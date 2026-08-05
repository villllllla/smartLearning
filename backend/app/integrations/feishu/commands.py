"""Parse Feishu text commands and execute via bot_facade."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Chat
from app.models.bot_session import BotSession
from app.services import bot_facade
from app.services.bot_session_service import (
    advance_queue,
    current_question_id,
    set_question_queue,
)

from . import formatters

log = logging.getLogger(__name__)

_DIFF_MAP = {
    "简单": "easy",
    "容易": "easy",
    "easy": "easy",
    "中等": "medium",
    "medium": "medium",
    "困难": "hard",
    "难": "hard",
    "hard": "hard",
}
_TYPE_MAP = {
    "概念": "concept",
    "八股": "concept",
    "concept": "concept",
    "场景": "scenario",
    "scenario": "scenario",
}


@dataclass
class CommandResult:
    texts: list[str]
    card: dict[str, Any] | None = None


def extract_message_text(content: str, message_type: str) -> str:
    if message_type != "text":
        return ""
    try:
        obj = json.loads(content)
        return (obj.get("text") or "").strip()
    except json.JSONDecodeError:
        return content.strip()


def parse_command_line(text: str) -> tuple[str, list[str]]:
    """Return (command_key, tokens)."""
    t = text.strip()
    if not t:
        return "", []
    # Button callback may pass JSON value
    if t.startswith("{") and "cmd" in t:
        try:
            obj = json.loads(t)
            cmd = obj.get("cmd", "")
            if cmd == "答案" and obj.get("qid"):
                return "答案", [str(obj["qid"])]
            return str(cmd), []
        except json.JSONDecodeError:
            pass

    parts = t.split()
    if parts[0] in ("帮助", "help", "?"):
        return "帮助", parts[1:]
    if parts[0] in ("题目", "出题", "quiz"):
        return "题目", parts[1:]
    if parts[0] in ("下一题", "next"):
        return "下一题", parts[1:]
    if parts[0] in ("答案", "answer"):
        return "答案", parts[1:]
    if parts[0] in ("对话", "chat", "问"):
        return "对话", parts[1:]
    if parts[0] in ("新建对话", "新对话", "reset"):
        return "新建对话", parts[1:]
    # 对话 without space: 对话你好
    if t.startswith("对话"):
        return "对话", [t[2:].strip()]
    return "未知", parts


def _parse_quiz_tokens(tokens: list[str]) -> dict[str, Any]:
    limit = 5
    mode = "random"
    difficulties: list[str] = []
    qtypes: list[str] = []
    tag_names: list[str] = []

    for tok in tokens:
        if re.fullmatch(r"\d+", tok):
            limit = max(1, min(50, int(tok)))
            continue
        if tok in ("错题", "wrong"):
            mode = "wrong"
            continue
        d = _DIFF_MAP.get(tok.lower()) or _DIFF_MAP.get(tok)
        if d:
            difficulties.append(d)
            continue
        qt = _TYPE_MAP.get(tok.lower()) or _TYPE_MAP.get(tok)
        if qt:
            qtypes.append(qt)
            continue
        if tok.startswith("标签:") or tok.startswith("标签："):
            raw = tok.split(":", 1)[-1].split("：", 1)[-1]
            tag_names.extend([x.strip() for x in raw.split(",") if x.strip()])

    return {
        "limit": limit,
        "mode": mode,
        "difficulties": difficulties,
        "qtypes": qtypes,
        "tag_names": tag_names,
    }


async def execute_command(
    db: Session,
    settings: Settings,
    session: BotSession,
    *,
    cmd: str,
    tokens: list[str],
) -> CommandResult:
    if cmd == "帮助":
        return CommandResult(texts=[formatters.help_text()])

    if cmd == "新建对话":
        chat = bot_facade.create_chat(db, title="飞书对话")
        session.smartlearning_chat_id = chat.id
        set_question_queue(session, [])
        db.commit()
        return CommandResult(texts=[f"已新建 LLM 会话 (chat_id={chat.id})。"])

    if cmd == "题目":
        opts = _parse_quiz_tokens(tokens)
        tag_ids = bot_facade.resolve_tag_ids_by_names(db, opts["tag_names"])
        if opts["tag_names"] and not tag_ids:
            return CommandResult(
                texts=[f"未找到标签: {', '.join(opts['tag_names'])}"]
            )
        questions = bot_facade.draw_questions(
            db,
            limit=opts["limit"],
            mode=opts["mode"],
            difficulties=opts["difficulties"] or None,
            qtypes=opts["qtypes"] or None,
            tag_ids=tag_ids or None,
        )
        ids = [q.id for q in questions]
        set_question_queue(session, ids)
        db.commit()
        hint = ""
        if opts["tag_names"]:
            hint = f" (标签: {','.join(opts['tag_names'])})"
        texts = formatters.format_questions_batch(questions, pool_hint=hint)
        card = None
        if ids:
            card = formatters.next_question_card(ids[0])
        return CommandResult(texts=texts, card=card)

    if cmd == "下一题":
        qid = advance_queue(session)
        db.commit()
        if qid is None:
            return CommandResult(texts=["当前没有题单。请先发送「题目 N」。"])
        pub = bot_facade.get_question_public(db, qid)
        if pub is None:
            return CommandResult(texts=[f"题目 {qid} 不存在。"])
        total = len(session.question_queue_json or [])
        idx = session.queue_cursor + 1
        return CommandResult(
            texts=[formatters.format_question_one(pub, index=idx, total=total)],
            card=formatters.next_question_card(qid),
        )

    if cmd == "答案":
        qid: int | None = None
        if tokens and tokens[0].isdigit():
            qid = int(tokens[0])
        else:
            qid = current_question_id(session)
        if qid is None:
            return CommandResult(texts=["请指定题目 ID,例如: 答案 12"])
        ans = bot_facade.get_answer(db, qid)
        if ans is None:
            return CommandResult(texts=[f"未找到题目 {qid}。"])
        return CommandResult(texts=formatters.format_answer(ans))

    if cmd == "对话":
        user_text = " ".join(tokens).strip()
        if not user_text:
            return CommandResult(texts=["用法: 对话 你的问题"])
        chat_id = session.smartlearning_chat_id
        chat: Chat | None = None
        if chat_id:
            chat = db.get(Chat, chat_id)
        if chat is None:
            chat = bot_facade.create_chat(db, title="飞书对话")
            session.smartlearning_chat_id = chat.id
            db.flush()
        try:
            reply = await bot_facade.chat_reply(db, chat, user_text)
        except Exception as exc:
            log.exception("bot chat failed")
            return CommandResult(texts=[f"对话失败: {exc}"])
        return CommandResult(texts=formatters.format_chat_reply(reply))

    return CommandResult(
        texts=[
            f"未识别命令: {cmd or '(空)'}\n发送「帮助」查看用法。",
        ]
    )


async def handle_incoming_text(
    db: Session,
    settings: Settings,
    *,
    open_id: str,
    chat_id: str,
    text: str,
) -> CommandResult:
    """Deprecated entry — delegates to agent router."""
    from . import agent

    return await agent.handle_incoming_text(
        db, settings, open_id=open_id, chat_id=chat_id, text=text
    )
