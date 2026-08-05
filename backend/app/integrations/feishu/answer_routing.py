"""Detect Feishu messages that submit a quiz answer (must include question id)."""
from __future__ import annotations

import re

from app.models.feishu_trigger import FeishuTriggerRule

from .commands import parse_command_line

# Extra phrases that are never treated as answer submissions (command-like).
_EXTRA_BLOCK_PREFIXES = (
    "给我",
    "来",
    "抽",
)

_MIN_ANSWER_LEN = 4

# Order matters: more specific patterns before bare ``{id} {body}``.
_SUBMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:作答|回答)\s*(\d{1,8})\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:题号|题目|题|ID|#)\s*(\d{1,8})\s+(.+)$", re.IGNORECASE),
    re.compile(r"^第\s*(\d{1,8})\s*题[：:\s]+(.+)$", re.IGNORECASE),
    re.compile(r"^(\d{1,8})\s*[：:]\s*(.+)$"),
    re.compile(r"^(\d{1,8})\s+(.+)$"),
)


def _blocked_as_command(
    text: str, trigger_rules: list[FeishuTriggerRule] | None = None
) -> bool:
    from app.services.feishu_trigger_service import (
        all_trigger_phrases,
        rules_from_defaults,
        try_direct_route,
    )

    t = text.strip()
    if t.startswith("{") and "cmd" in t:
        return True
    rules = trigger_rules or rules_from_defaults()
    low = t.lower()
    for prefix in all_trigger_phrases(rules) + list(_EXTRA_BLOCK_PREFIXES):
        if t.startswith(prefix) or low.startswith(prefix.lower()):
            return True
    cmd, _tokens = parse_command_line(t)
    if cmd in ("帮助", "题目", "答案", "下一题", "对话"):
        return True
    return try_direct_route(t, rules) is not None


def parse_answer_submission(
    text: str, *, trigger_rules: list[FeishuTriggerRule] | None = None
) -> tuple[int, str] | None:
    """Parse ``question_id`` + answer body. Returns None if format invalid."""
    t = (text or "").strip()
    if not t or _blocked_as_command(t, trigger_rules):
        return None
    for pat in _SUBMIT_PATTERNS:
        m = pat.match(t)
        if not m:
            continue
        qid = int(m.group(1))
        body = (m.group(2) or "").strip()
        if len(body) >= _MIN_ANSWER_LEN:
            return qid, body
    return None


def should_submit_as_answer(
    text: str,
    *,
    has_current_question: bool = True,
    trigger_rules: list[FeishuTriggerRule] | None = None,
) -> bool:
    """True only when the message explicitly includes a question id + answer body."""
    _ = has_current_question
    return parse_answer_submission(text, trigger_rules=trigger_rules) is not None


def parse_learning_note(
    text: str, trigger_rules: list[FeishuTriggerRule] | None = None
) -> str | None:
    """If a configured prefix matches, return the note body, else None."""
    from app.services.feishu_trigger_service import (
        resolve_trigger,
        rules_from_defaults,
    )

    rules = trigger_rules or rules_from_defaults()
    resolved = resolve_trigger(text, rules)
    if resolved is None:
        return None
    tool, args = resolved
    if tool != "submit_learning_note":
        return None
    return args.get("raw_input")
