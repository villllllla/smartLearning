"""Natural-language agent router for Feishu (all user text goes through LLM tool selection)."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.bot_session import BotSession
from app.services import todo_service
from app.services.bot_session_service import current_question_id, get_or_create_session
from app.services.feishu_trigger_service import get_rules, try_direct_route
from app.services.llm import LLMClient, LLMError, LLMMessage

from .answer_routing import parse_answer_submission
from .commands import CommandResult, parse_command_line
from .tools import execute_tool, list_tag_names

_REVIEW_CARD_CMDS = {"复习要点": "note_reveal", "复习掌握": "note_master", "复习加强": "note_reinforce"}
_TODO_CARD_CMDS = {
    "todo_done": "todo_done",
    "todo_snooze": "todo_snooze",
    "todo_hold": "todo_hold",
}
_TODO_INTERRUPT_TOOLS = frozenset(
    {"help", "reply_only", "push_now", "get_push_config", "list_todos"}
)


def _parse_todo_card(text: str) -> tuple[str, int] | None:
    t = (text or "").strip()
    if not (t.startswith("{") and "cmd" in t):
        return None
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        return None
    tool = _TODO_CARD_CMDS.get(str(obj.get("cmd", "")))
    tid = obj.get("tid")
    if tool is None or tid is None:
        return None
    try:
        return tool, int(tid)
    except (TypeError, ValueError):
        return None


def _interrupts_todo_clarification(text: str, rules) -> bool:
    from app.services.feishu_trigger_service import resolve_trigger

    resolved = resolve_trigger(text, rules)
    if resolved is not None and resolved[0] in _TODO_INTERRUPT_TOOLS:
        return True
    if parse_answer_submission(text, trigger_rules=rules) is not None:
        return True
    return False


def _parse_review_card(text: str) -> tuple[str, int] | None:
    """Return (tool, note_id) for review-card button callbacks, else None."""
    t = (text or "").strip()
    if not (t.startswith("{") and "cmd" in t):
        return None
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        return None
    tool = _REVIEW_CARD_CMDS.get(str(obj.get("cmd", "")))
    nid = obj.get("nid")
    if tool is None or nid is None:
        return None
    try:
        return tool, int(nid)
    except (TypeError, ValueError):
        return None

log = logging.getLogger(__name__)

# Uses chat_general binding for model/provider; system prompt is defined here.
_AGENT_SCENE = "chat_general"

AGENT_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tool"],
    "properties": {
        "tool": {
            "type": "string",
            "enum": [
                "draw_questions",
                "show_answer",
                "next_question",
                "reset_chat",
                "chat",
                "help",
                "reply_only",
                "get_push_config",
                "update_push_config",
                "push_now",
                "submit_answer",
                "submit_learning_note",
                "submit_todo",
                "list_todos",
            ],
        },
        "args": {
            "type": "object",
            "additionalProperties": True,
        },
        "message": {
            "type": "string",
            "description": "Optional user-facing note when tool is reply_only",
        },
    },
    "additionalProperties": False,
}


def _friendly_llm_error(exc: LLMError) -> str:
    msg = str(exc)
    low = msg.lower()
    if (
        "authorization" in low
        or "api key" in low
        or "apikey" in low
        or "401" in msg
        or "403" in msg
    ):
        return (
            "模型 API Key 无效或未配置。"
            "请到 Web「设置 → 模型与 Provider」为 chat_general 使用的 Provider "
            "重新填写 API Key → 保存 → 点「连通性测试」通过后再试。"
        )
    if "无法连接 provider" in low or "network error" in low or "connect" in low:
        return (
            f"{msg} "
            "请到 Web「设置 → 模型与 Provider」对 Gemini 点「连通性测试」；"
            "若 Web 能通而飞书仍失败，请用同一终端启动 uvicorn 并配置 HTTPS_PROXY。"
        )
    if len(msg) > 400:
        return msg[:400] + "…"
    return msg


def _build_system_prompt(*, tag_names: list[str], session: BotSession) -> str:
    tags_hint = ", ".join(tag_names[:60]) if tag_names else "(暂无标签)"
    qid = current_question_id(session)
    qlen = len(session.question_queue_json or [])
    cursor = session.queue_cursor
    return f"""你是 SmartLearning 飞书助手的「意图路由器」。根据用户最新一句话,选择唯一一个 tool 并填写 args。
只输出一个 JSON 对象,不要 markdown 代码块,不要其它文字。

## 可用 tool
- draw_questions: 从题库抽题给用户练习。args: limit(1-20整数,默认5), mode(random|wrong|sequential,默认random),
  difficulties(可选数组: easy|medium|hard), qtypes(可选数组: concept|scenario),
  tag_names(可选字符串数组,须从下方标签库选)。抽题时禁止在 message 里写标准答案。
- show_answer: 查看某题标准答案。args: question_id(可选整数;省略则用当前题)。
- next_question: 题单下一题(仅题干)。args 可为 {{}}。
- reset_chat: 清空 LLM 对话上下文。args 可为 {{}}。
- chat: 一般知识问答、解释概念、闲聊(不抽题、不查库答案)。args: message(用户问题原文)。
- help: 显示能力说明。args 可为 {{}}。
- get_push_config: 查看定时推题配置。args 可为 {{}}。
- update_push_config: 修改定时推题。args 可选: enabled(bool), push_times(字符串数组如["09:00","18:00"]), frequency(daily|weekdays|weekly), limit(1-20), mode(random|sequential|wrong), difficulties, qtypes, tag_names。
- push_now: 立即按当前配置推送面试题到飞书。args 可为 {{}}。
- submit_answer: 用户提交某题作答并评分入库。args: question_id(必填整数), user_answer(必填,不含题号前缀的作答正文)。
- submit_learning_note: 用户提交「今日/本次学习总结、学习心得、学到的内容」,需检验并结构化保存。args: raw_input(必填,用户总结原文)。
- submit_todo: 用户要创建待办/设置提醒,如「明天3点提醒我交周报」。args: raw_input(必填)。信息不全时由服务端追问,不要在此替用户编造时间。
- list_todos: 用户要查看待办列表。无 args。
- reply_only: 简短回复、澄清、无法执行时说明。args/message: 写给用户的文字。

## 规则
1. 「五道/5道/来5题」等 → draw_questions, limit=5, 不要询问确认,直接抽题。
2. 「困难/简单/中等」「八股/概念/场景」「错题」→ 填入 difficulties/qtypes/mode=wrong。
3. 「答案/解析 题目12」→ show_answer, question_id=12。
4. 「下一题」→ next_question。
5. 「新建对话/清空上下文」→ reset_chat。
6. 明确问知识且与题库无关 → chat; 将用户原话放入 args.message。
7. 仅当用户明确带题号提交作答(如「15 我的答案…」「作答 15 …」「题号15 …」) → submit_answer, 解析出 question_id 与 user_answer(去掉题号前缀)。未带题号的提问/闲聊 → chat, 不要 submit_answer。
8. 用户在做「学习总结/学习心得/今天学了什么」的较长陈述(常以「总结/学习总结/今日总结/笔记」开头) → submit_learning_note, raw_input=用户原文(去掉前缀)。注意与「提问」区分:提问用 chat。
9. 用户要设置待办/提醒(含时间+事项,如「周五提醒我复习Redis」「待办:交周报」) → submit_todo, raw_input=用户原文。
10. 用户要查看待办/提醒列表 → list_todos。
11. 题库标签(名称精确匹配): {tags_hint}

## 当前会话
- 题单长度: {qlen}, 游标: {cursor}, 当前题 ID: {qid or "无"}
"""


async def run_agent(
    db: Session,
    settings: Settings,
    session: BotSession,
    *,
    user_text: str,
) -> CommandResult:
    text = (user_text or "").strip()
    if not text:
        return CommandResult(texts=["请输入内容。"])

    try:
        client, _prompt = LLMClient.for_scene(db, _AGENT_SCENE, tenant_id=1)
    except LLMError as exc:
        return CommandResult(texts=[f"Agent 未配置模型: {exc}"])

    tags = list_tag_names(db)
    system = _build_system_prompt(tag_names=tags, session=session)
    messages = [
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content=text),
    ]
    try:
        data, _resp = await client.chat_json(messages, schema=AGENT_ACTION_SCHEMA)
    except LLMError as exc:
        log.warning("feishu agent LLM failed: %s", exc)
        return CommandResult(texts=[f"理解失败: {_friendly_llm_error(exc)}"])

    tool = str(data.get("tool") or "reply_only")
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    if data.get("message"):
        if tool == "reply_only":
            args = {**args, "message": data["message"]}
        elif tool == "chat" and not args.get("message"):
            args = {**args, "message": data["message"]}
    if tool == "chat" and not args.get("message"):
        args["message"] = text

    log.info("feishu agent tool=%s args=%s", tool, args)
    return await execute_tool(db, session, tool, args, user_text=text)


def _is_card_callback(text: str) -> bool:
    t = text.strip()
    return t.startswith("{") and "cmd" in t


async def handle_incoming_text(
    db: Session,
    settings: Settings,
    *,
    open_id: str,
    chat_id: str,
    text: str,
    message_id: str | None = None,
) -> CommandResult:
    """All natural language → agent; interactive card JSON → direct tool."""
    session = get_or_create_session(
        db, platform="feishu", feishu_open_id=open_id, feishu_chat_id=chat_id
    )
    rules = get_rules(db, tenant_id=1)

    review_cb = _parse_review_card(text)
    if review_cb is not None:
        tool, nid = review_cb
        return await execute_tool(db, session, tool, {"note_id": nid}, user_text=text)

    todo_cb = _parse_todo_card(text)
    if todo_cb is not None:
        tool, tid = todo_cb
        return await execute_tool(db, session, tool, {"todo_id": tid}, user_text=text)

    clarifying = todo_service.get_clarifying_todo(db, feishu_open_id=open_id)
    if clarifying is not None and not _interrupts_todo_clarification(text, rules):
        if todo_service.is_todo_cancel(text):
            clarifying.status = "cancelled"
            db.commit()
            return CommandResult(texts=["已取消,未创建待办。"])
        result = await todo_service.handle_todo_message(
            db,
            user_message=text,
            feishu_open_id=open_id,
            feishu_message_id=message_id,
            existing=clarifying,
        )
        db.commit()
        return CommandResult(texts=result.texts, card=result.card)

    submission = parse_answer_submission(text, trigger_rules=rules)
    if submission is not None:
        qid, answer_body = submission
        return await execute_tool(
            db,
            session,
            "submit_answer",
            {
                "question_id": qid,
                "user_answer": answer_body,
                "feishu_message_id": message_id,
            },
            user_text=text,
        )

    direct = try_direct_route(text, rules)
    if direct is not None:
        tool, args = direct
        if tool == "submit_learning_note" and message_id:
            args = {**args, "feishu_message_id": message_id}
        if tool in ("submit_todo", "list_todos") and message_id:
            args = {**args, "feishu_message_id": message_id}
        return await execute_tool(db, session, tool, args, user_text=text)

    if _is_card_callback(text):
        cmd, tokens = parse_command_line(text)
        if cmd == "帮助":
            return await execute_tool(db, session, "help", {})
        if cmd == "新建对话":
            return await execute_tool(db, session, "reset_chat", {})
        if cmd == "题目":
            from .commands import _parse_quiz_tokens

            opts = _parse_quiz_tokens(tokens)
            return await execute_tool(
                db,
                session,
                "draw_questions",
                {
                    "limit": opts["limit"],
                    "mode": opts["mode"],
                    "difficulties": opts["difficulties"],
                    "qtypes": opts["qtypes"],
                    "tag_names": opts["tag_names"],
                },
            )
        if cmd == "下一题":
            return await execute_tool(db, session, "next_question", {})
        if cmd == "答案":
            qid = int(tokens[0]) if tokens and tokens[0].isdigit() else None
            return await execute_tool(
                db, session, "show_answer", {"question_id": qid} if qid else {}
            )

    return await run_agent(db, settings, session, user_text=text)
