"""Execute Feishu bot tools (used by rigid card callbacks and the agent)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chat, Question
from app.models.bot_session import BotSession
from app.models.question import Tag
from app.services import bot_facade, learning_note_service, todo_service
from app.services.bot_session_service import (
    advance_queue,
    current_question_id,
    set_question_queue,
)
from app.services.llm import LLMError
from app.services.push_schedule_service import (
    execute_push,
    get_or_create_schedule,
    schedule_summary,
    update_schedule,
)
from app.services.scoring_service import score_answer

from . import formatters
from .commands import CommandResult

log = logging.getLogger(__name__)

_VALID_MODES = frozenset({"random", "wrong", "sequential"})
_VALID_DIFF = frozenset({"easy", "medium", "hard"})
_VALID_QTYPE = frozenset({"concept", "scenario"})


def list_tag_names(db: Session, *, limit: int = 80) -> list[str]:
    rows = db.execute(select(Tag.name).order_by(Tag.name.asc()).limit(limit)).scalars().all()
    return list(rows)


async def execute_tool(
    db: Session,
    session: BotSession,
    tool: str,
    args: dict[str, Any] | None,
    *,
    user_text: str = "",
) -> CommandResult:
    args = args or {}
    tool = (tool or "").strip().lower()

    if tool == "help":
        return CommandResult(texts=[formatters.help_text()])

    if tool == "get_push_config":
        row = get_or_create_schedule(db, tenant_id=1)
        return CommandResult(texts=[schedule_summary(row)])

    if tool == "update_push_config":
        tag_names = _norm_str_list(args.get("tag_names"))
        tag_ids = bot_facade.resolve_tag_ids_by_names(db, tag_names) if tag_names else None
        fields: dict = {}
        if "enabled" in args:
            fields["enabled"] = bool(args["enabled"])
        if args.get("push_times") is not None:
            fields["push_times"] = _norm_str_list(args.get("push_times"))
        if args.get("frequency"):
            fields["frequency"] = str(args["frequency"]).lower()
        if args.get("limit") is not None:
            fields["limit"] = _clamp_int(args.get("limit"), default=3, lo=1, hi=20)
        if args.get("mode"):
            fields["mode"] = str(args["mode"]).lower()
        if args.get("difficulties") is not None:
            fields["difficulties"] = _norm_list(args.get("difficulties"), _VALID_DIFF)
        if args.get("qtypes") is not None:
            fields["qtypes"] = _norm_list(args.get("qtypes"), _VALID_QTYPE)
        if tag_ids is not None:
            fields["tag_ids"] = tag_ids
        try:
            row = update_schedule(db, tenant_id=1, **fields)
            db.commit()
        except ValueError as exc:
            return CommandResult(texts=[str(exc)])
        return CommandResult(texts=[f"已更新定时推题配置。\n{schedule_summary(row)}"])

    if tool == "push_now":
        row = get_or_create_schedule(db, tenant_id=1)
        try:
            _, _, msg = await execute_push(db, row, manual=True)
            db.commit()
        except Exception as exc:
            return CommandResult(texts=[f"推送失败: {exc}"])
        return CommandResult(texts=[msg])

    if tool == "fetch_ai_news":
        from app.services import ai_news_service

        news_row = ai_news_service.get_or_create_schedule(db, tenant_id=1)
        try:
            count, _, msg, _ = await ai_news_service.execute_news_push(
                db, news_row, manual=True
            )
            db.commit()
        except Exception as exc:
            return CommandResult(texts=[f"AI 资讯抓取失败: {exc}"])
        return CommandResult(texts=[msg])

    if tool == "reset_chat":
        chat = bot_facade.create_chat(db, title="飞书对话")
        session.smartlearning_chat_id = chat.id
        set_question_queue(session, [])
        db.commit()
        return CommandResult(texts=["已新建对话上下文,之前的 LLM 聊天记录已清空。"])

    if tool == "draw_questions":
        limit = _clamp_int(args.get("limit"), default=5, lo=1, hi=20)
        mode = str(args.get("mode") or "random").lower()
        if mode not in _VALID_MODES:
            mode = "random"
        difficulties = _norm_list(args.get("difficulties"), _VALID_DIFF)
        qtypes = _norm_list(args.get("qtypes"), _VALID_QTYPE)
        tag_names = _norm_str_list(args.get("tag_names"))
        tag_ids = bot_facade.resolve_tag_ids_by_names(db, tag_names)
        if tag_names and not tag_ids:
            return CommandResult(texts=[f"未找到标签: {', '.join(tag_names)}"])
        questions = bot_facade.draw_questions(
            db,
            limit=limit,
            mode=mode,
            difficulties=difficulties or None,
            qtypes=qtypes or None,
            tag_ids=tag_ids or None,
        )
        ids = [q.id for q in questions]
        set_question_queue(session, ids)
        db.commit()
        hint = ""
        if tag_names:
            hint = f" (标签: {','.join(tag_names)})"
        if mode == "wrong":
            hint += " [错题模式]"
        texts = formatters.format_questions_batch(questions, pool_hint=hint)
        card = formatters.next_question_card(ids[0]) if ids else None
        return CommandResult(texts=texts, card=card)

    if tool == "next_question":
        qid = advance_queue(session)
        db.commit()
        if qid is None:
            return CommandResult(texts=["当前没有题单。可以说「给我 5 道题」先抽题。"])
        pub = bot_facade.get_question_public(db, qid)
        if pub is None:
            return CommandResult(texts=[f"题目 {qid} 不存在。"])
        total = len(session.question_queue_json or [])
        idx = min(session.queue_cursor + 1, total)
        return CommandResult(
            texts=[formatters.format_question_one(pub, index=idx, total=total)],
            card=formatters.next_question_card(qid),
        )

    if tool == "submit_answer":
        user_answer = (args.get("user_answer") or user_text or "").strip()
        if not user_answer:
            return CommandResult(
                texts=[
                    "作答不能为空。须带题号，例如：\n"
                    "· 15 你的作答正文…\n"
                    "· 作答 15 你的作答正文…\n"
                    "· 题号15 你的作答正文…"
                ]
            )
        qid = args.get("question_id")
        if qid is not None:
            try:
                qid = int(qid)
            except (TypeError, ValueError):
                qid = None
        if qid is None:
            parsed = None
            from .answer_routing import parse_answer_submission

            if user_text:
                parsed = parse_answer_submission(user_text)
            if parsed is not None:
                qid, user_answer = parsed
            else:
                return CommandResult(
                    texts=[
                        "提交作答须带题号，例如：\n"
                        "· 15 你的作答正文…\n"
                        "· 作答 15 你的作答正文…\n"
                        "未带题号的消息会按「对话/提问」处理，不会记入练习。"
                    ]
                )
        question = db.get(Question, qid)
        if question is None or question.deleted_at is not None:
            return CommandResult(texts=[f"题目 {qid} 不存在。"])
        feishu_message_id = args.get("feishu_message_id")
        if feishu_message_id is not None:
            feishu_message_id = str(feishu_message_id)
        try:
            attempt = await score_answer(
                db,
                question=question,
                user_answer=user_answer,
                channel="feishu",
                feishu_open_id=session.feishu_open_id,
                feishu_message_id=feishu_message_id,
                bot_session_id=session.id,
            )
            db.commit()
        except LLMError as exc:
            return CommandResult(texts=[f"评分失败: {exc}"])
        pub = bot_facade.get_question_public(db, qid)
        if pub is None:
            return CommandResult(texts=[f"题目 {qid} 不存在。"])
        log.info(
            "feishu answer recorded attempt_id=%s question_id=%s open_id=%s grade=%s",
            attempt.id,
            qid,
            session.feishu_open_id,
            attempt.grade,
        )
        return CommandResult(
            texts=formatters.format_scoring_result(pub, attempt, user_answer=user_answer),
            card=formatters.next_question_card(qid),
        )

    if tool == "submit_learning_note":
        raw = (args.get("raw_input") or user_text or "").strip()
        if len(raw) < 8:
            return CommandResult(
                texts=[
                    "学习总结内容太短。请用「总结 今天学了…」发送一段较完整的学习心得,"
                    "我会帮你检验、结构化并加入复习计划。"
                ]
            )
        feishu_message_id = args.get("feishu_message_id")
        if feishu_message_id is not None:
            feishu_message_id = str(feishu_message_id)
        try:
            note = await learning_note_service.create_note(
                db,
                raw_input=raw,
                tenant_id=1,
                channel="feishu",
                feishu_open_id=session.feishu_open_id,
                feishu_message_id=feishu_message_id,
            )
            db.commit()
        except LLMError as exc:
            return CommandResult(texts=[f"结构化失败: {exc}"])
        except Exception as exc:  # noqa: BLE001
            log.exception("submit_learning_note failed")
            return CommandResult(texts=[f"保存学习总结失败: {exc}"])
        log.info(
            "feishu learning note saved id=%s open_id=%s", note.id, session.feishu_open_id
        )
        return CommandResult(texts=formatters.format_note_saved(note))

    if tool in ("submit_todo", "list_todos"):
        raw = (args.get("raw_input") or user_text or "").strip()
        try:
            if tool == "list_todos":
                result = await todo_service.handle_todo_message(
                    db,
                    user_message="待办列表",
                    tenant_id=1,
                    feishu_open_id=session.feishu_open_id,
                    feishu_message_id=args.get("feishu_message_id"),
                )
            else:
                result = await todo_service.handle_todo_message(
                    db,
                    user_message=raw,
                    tenant_id=1,
                    feishu_open_id=session.feishu_open_id,
                    feishu_message_id=args.get("feishu_message_id"),
                )
            db.commit()
        except LLMError as exc:
            return CommandResult(texts=[f"待办解析失败: {exc}"])
        except Exception as exc:  # noqa: BLE001
            log.exception("submit_todo failed")
            return CommandResult(texts=[f"待办处理失败: {exc}"])
        return CommandResult(texts=result.texts, card=result.card)

    if tool in ("todo_done", "todo_snooze"):
        tid = args.get("todo_id")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return CommandResult(texts=["无效的待办卡片。"])
        item = todo_service.get_todo(db, tid, tenant_id=1)
        if item is None:
            return CommandResult(texts=[f"未找到待办 #{tid}"])
        if tool == "todo_done":
            todo_service.mark_done(db, item)
            db.commit()
            return CommandResult(texts=[f"✅ 待办 #{tid}「{item.title}」已标记完成。"])
        from datetime import datetime, timedelta

        item.remind_at = datetime.utcnow() + timedelta(hours=1)
        item.status = "scheduled"
        db.commit()
        return CommandResult(texts=[f"已推迟 1 小时后再提醒「{item.title}」。"])

    if tool == "todo_hold":
        from datetime import date, timedelta

        tid = args.get("todo_id")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return CommandResult(texts=["无效的待办卡片。"])
        item = todo_service.get_todo(db, tid, tenant_id=1)
        if item is None:
            return CommandResult(texts=[f"未找到待办 #{tid}"])
        until = date.today() + timedelta(days=3)
        todo_service.snooze_todo(db, item, until=until, note="飞书快捷挂起")
        db.commit()
        return CommandResult(
            texts=[
                f"⏸ 已挂起「{item.title}」至 {until.isoformat()}。"
                "如需自定义日期/备注,可在网页「待办」里调整。"
            ]
        )

    if tool in ("note_reveal", "note_master", "note_reinforce"):
        nid = args.get("note_id")
        try:
            nid = int(nid)
        except (TypeError, ValueError):
            return CommandResult(texts=["无效的复习卡片。"])
        note = learning_note_service.get_note(db, nid, tenant_id=1)
        if note is None:
            return CommandResult(texts=[f"未找到学习总结 {nid}（可能已删除）。"])
        if tool == "note_reveal":
            return CommandResult(texts=formatters.format_note_reveal(note))
        if tool == "note_master":
            learning_note_service.mark_mastered(db, note, True)
            db.commit()
            from datetime import datetime

            when = "以更低频率抽查"
            if note.next_review_at:
                secs = (note.next_review_at - datetime.utcnow()).total_seconds()
                when = f"约 {max(1, round(secs / 86400))} 天后再抽查一次"
            return CommandResult(
                texts=[
                    f"👍 已将《{note.title}》标记为已掌握,复习频率大幅降低({when}),"
                    "不会彻底停推。"
                ]
            )
        learning_note_service.reset_review(db, note)
        db.commit()
        return CommandResult(texts=[f"已安排《{note.title}》尽快再次复习,加油。"])

    if tool == "show_answer":
        qid = args.get("question_id")
        if qid is not None:
            try:
                qid = int(qid)
            except (TypeError, ValueError):
                qid = None
        if qid is None:
            qid = current_question_id(session)
        if qid is None:
            return CommandResult(texts=["请说明题目 ID,或先抽题。"])
        ans = bot_facade.get_answer(db, qid)
        if ans is None:
            return CommandResult(texts=[f"未找到题目 {qid}。"])
        return CommandResult(texts=formatters.format_answer(ans))

    if tool == "chat":
        msg = (args.get("message") or user_text or "").strip()
        if not msg:
            return CommandResult(texts=["请说明你想聊的内容。"])
        chat_id = session.smartlearning_chat_id
        chat: Chat | None = db.get(Chat, chat_id) if chat_id else None
        if chat is None:
            chat = bot_facade.create_chat(db, title="飞书对话")
            session.smartlearning_chat_id = chat.id
            db.flush()
        try:
            from app.core.config import get_settings

            use_rag = get_settings().rag_enabled and get_settings().rag_default_in_chat
            reply = await bot_facade.chat_reply(db, chat, msg, use_rag=use_rag)
        except Exception as exc:
            log.exception("agent chat failed")
            return CommandResult(texts=[f"对话失败: {exc}"])
        return CommandResult(texts=formatters.format_chat_reply(reply))

    if tool == "reply_only":
        msg = (args.get("message") or "").strip()
        return CommandResult(texts=formatters.format_chat_reply(msg or "好的。"))

    return CommandResult(
        texts=[
            "暂时无法处理该请求。你可以说: 给我 5 道场景题 / 答案 12 / 下一题 / 解释某个知识点。"
        ]
    )


def _clamp_int(v: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _norm_list(v: Any, allowed: frozenset[str]) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        s = str(item).lower().strip()
        if s in allowed and s not in out:
            out.append(s)
    return out


def _norm_str_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]
