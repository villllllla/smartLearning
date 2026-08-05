"""Load / resolve / update configurable Feishu trigger prefixes."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feishu_trigger import FeishuTriggerRule

_CONNECTIVITY_MESSAGE = (
    "SmartLearning 飞书 Bot 已连通，可正常使用。发送「帮助」查看能力。"
)

DEFAULT_FEISHU_TRIGGER_RULES: tuple[dict[str, Any], ...] = (
    {
        "action": "submit_learning_note",
        "title": "学习总结",
        "description": "前缀 + 正文：检验、结构化保存并加入间隔复习",
        "match_mode": "prefix",
        "prefixes": ["学习总结", "今日总结", "总结", "学习笔记", "笔记", "note"],
        "extra_args_json": {"min_body_len": 8},
        "priority": 10,
    },
    {
        "action": "submit_todo",
        "title": "创建待办",
        "description": "前缀 + 正文：意图识别、拆解并设置提醒(可追问补全)",
        "match_mode": "prefix",
        "prefixes": ["待办", "提醒", "todo", "remind"],
        "extra_args_json": {"min_body_len": 4},
        "priority": 15,
    },
    {
        "action": "list_todos",
        "title": "待办列表",
        "description": "查看未完成待办",
        "match_mode": "exact",
        "prefixes": ["待办列表", "我的待办", "todo list"],
        "extra_args_json": {},
        "priority": 84,
    },
    {
        "action": "fetch_ai_news",
        "title": "AI 资讯",
        "description": "立即抓取多源 AI 资讯并推送今日热点 Top5",
        "match_mode": "exact",
        "prefixes": ["资讯", "AI资讯", "ai资讯", "热点", "今日热点", "ai news"],
        "extra_args_json": {},
        "priority": 82,
    },
    {
        "action": "help",
        "title": "帮助",
        "description": "查看飞书 Bot 能力说明",
        "match_mode": "exact",
        "prefixes": ["帮助", "help", "?", "？"],
        "extra_args_json": {},
        "priority": 100,
    },
    {
        "action": "get_push_config",
        "title": "推送设置",
        "description": "查看面试题定时推送配置",
        "match_mode": "exact",
        "prefixes": ["推送设置", "定时推送", "查看推送"],
        "extra_args_json": {},
        "priority": 90,
    },
    {
        "action": "reply_only",
        "title": "连通测试",
        "description": "快捷连通性测试（不走 LLM/RAG）",
        "match_mode": "exact",
        "prefixes": ["测试连接", "测试连通性", "连通性测试", "ping"],
        "extra_args_json": {"message": _CONNECTIVITY_MESSAGE},
        "priority": 95,
    },
    {
        "action": "push_now",
        "title": "立即推题",
        "description": "立即从题库抽题并推送到飞书",
        "match_mode": "exact",
        "prefixes": ["立即推题", "立即推送", "现在推题", "推送一题", "推题"],
        "extra_args_json": {},
        "priority": 80,
    },
    {
        "action": "next_question",
        "title": "下一题",
        "description": "练习队列中的下一道题",
        "match_mode": "exact",
        "prefixes": ["下一题", "next"],
        "extra_args_json": {},
        "priority": 70,
    },
    {
        "action": "reset_chat",
        "title": "新建对话",
        "description": "清空飞书聊天上下文",
        "match_mode": "exact",
        "prefixes": ["新建对话", "新对话", "reset"],
        "extra_args_json": {},
        "priority": 60,
    },
)

_SEPARATORS = "：:，,、 \n\t"

# Actions whose prefixes overlap with plain questions (e.g. "总结一下 X 有哪些
# 数据结构" starts with the "总结" note-taking prefix but is really a question).
# For these, a question-shaped body must not be swallowed by the prefix match —
# fall through so the LLM intent router handles it as `chat` instead.
_QUESTION_GATED_ACTIONS = frozenset({"submit_learning_note", "submit_todo"})
_QUESTION_MARKERS = (
    "吗", "呢",
    "什么", "为什么", "怎么", "怎样", "如何",
    "哪些", "哪个", "哪儿", "哪里",
    "是不是", "有没有", "多少",
)


def _looks_like_question(body: str, *, separated: bool) -> bool:
    """Whether a gated prefix hit is really a question rather than a command.

    ``separated`` means the trigger word was followed by a separator ("总结 今天
    学了…"), i.e. the user issued it as a command — then only an explicit "?"
    overrides. Without a separator the prefix ran on into a sentence ("总结一下
    Redis 有哪些数据结构"), which is where interrogatives are a real signal.

    Scanning for interrogatives unconditionally would swallow ordinary notes:
    "总结 今天搞清楚了 MVCC 怎么做可见性判断" is a statement that happens to
    contain "怎么".
    """
    tail = body.rstrip()
    if tail.endswith("？") or tail.endswith("?"):
        return True
    if separated:
        return False
    return any(marker in body for marker in _QUESTION_MARKERS)


def normalize_prefix_list(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        for part in re.split(r"[,，\n]+", str(item)):
            p = part.strip()
            if not p:
                continue
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


def rules_from_defaults() -> list[FeishuTriggerRule]:
    """In-memory default rules (tests / answer blocking without DB)."""
    return [
        FeishuTriggerRule(
            tenant_id=1,
            action=spec["action"],
            title=spec["title"],
            description=spec.get("description"),
            match_mode=spec["match_mode"],
            prefixes=list(spec["prefixes"]),
            extra_args_json=deepcopy(spec.get("extra_args_json") or {}),
            enabled=True,
            priority=int(spec.get("priority") or 0),
            is_system=True,
        )
        for spec in DEFAULT_FEISHU_TRIGGER_RULES
    ]


def get_rules(db: Session, *, tenant_id: int) -> list[FeishuTriggerRule]:
    rows = list(
        db.execute(
            select(FeishuTriggerRule)
            .where(FeishuTriggerRule.tenant_id == tenant_id)
            .order_by(FeishuTriggerRule.priority.desc(), FeishuTriggerRule.id.asc())
        ).scalars().all()
    )
    if rows:
        return rows
    return seed_default_rules(db, tenant_id=tenant_id)


def seed_default_rules(db: Session, *, tenant_id: int) -> list[FeishuTriggerRule]:
    created: list[FeishuTriggerRule] = []
    for spec in DEFAULT_FEISHU_TRIGGER_RULES:
        row = FeishuTriggerRule(
            tenant_id=tenant_id,
            action=spec["action"],
            title=spec["title"],
            description=spec.get("description"),
            match_mode=spec["match_mode"],
            prefixes=list(spec["prefixes"]),
            extra_args_json=deepcopy(spec.get("extra_args_json") or {}),
            enabled=True,
            priority=int(spec.get("priority") or 0),
            is_system=True,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def reset_rules_to_defaults(db: Session, *, tenant_id: int) -> list[FeishuTriggerRule]:
    db.execute(
        FeishuTriggerRule.__table__.delete().where(
            FeishuTriggerRule.tenant_id == tenant_id
        )
    )
    db.flush()
    return seed_default_rules(db, tenant_id=tenant_id)


def update_rules(
    db: Session,
    *,
    tenant_id: int,
    updates: list[dict[str, Any]],
) -> list[FeishuTriggerRule]:
    existing = {r.action: r for r in get_rules(db, tenant_id=tenant_id)}
    for item in updates:
        action = str(item.get("action") or "").strip()
        if not action or action not in existing:
            raise ValueError(f"未知或未注册的触发动作: {action}")
        row = existing[action]
        if item.get("enabled") is not None:
            row.enabled = bool(item["enabled"])
        if item.get("prefixes") is not None:
            prefixes = normalize_prefix_list(list(item["prefixes"]))
            if not prefixes:
                raise ValueError(f"「{row.title}」至少保留一个触发短语")
            row.prefixes = prefixes
        if item.get("match_mode") is not None:
            mode = str(item["match_mode"]).strip().lower()
            if mode not in ("prefix", "exact"):
                raise ValueError("match_mode 须为 prefix 或 exact")
            row.match_mode = mode
    db.flush()
    return get_rules(db, tenant_id=tenant_id)


def all_trigger_phrases(rules: list[FeishuTriggerRule]) -> list[str]:
    phrases: list[str] = []
    for rule in rules:
        if not rule.enabled:
            continue
        phrases.extend(str(p) for p in (rule.prefixes or []) if str(p).strip())
    return phrases


def resolve_trigger(
    text: str, rules: list[FeishuTriggerRule]
) -> tuple[str, dict[str, Any]] | None:
    """Match user text against enabled rules. Returns (tool, args) or None."""
    t = (text or "").strip()
    if not t or (t.startswith("{") and "cmd" in t):
        return None

    enabled = [r for r in rules if r.enabled and r.prefixes]

    for rule in sorted(enabled, key=lambda r: (-r.priority, r.id)):
        if rule.match_mode != "exact":
            continue
        for phrase in rule.prefixes:
            p = str(phrase).strip()
            if not p:
                continue
            if t.lower() == p.lower():
                return rule.action, dict(rule.extra_args_json or {})

    best: tuple[int, int, FeishuTriggerRule, str, bool] | None = None
    for rule in enabled:
        if rule.match_mode != "prefix":
            continue
        for phrase in rule.prefixes:
            p = str(phrase).strip()
            if not p:
                continue
            if t.lower().startswith(p.lower()):
                raw_tail = t[len(p) :]
                body = raw_tail.lstrip(_SEPARATORS)
                # Command form: the trigger word was written as its own token.
                separated = raw_tail == "" or raw_tail[0] in _SEPARATORS
                key = (len(p), rule.priority)
                if best is None or key > (best[0], best[1]):
                    best = (len(p), rule.priority, rule, body, separated)

    if best is None:
        return None

    rule = best[2]
    body = best[3]
    if rule.action in _QUESTION_GATED_ACTIONS and _looks_like_question(
        body, separated=best[4]
    ):
        return None
    args = dict(rule.extra_args_json or {})
    if rule.action == "submit_learning_note":
        min_len = int(args.pop("min_body_len", 8))
        if len(body) < min_len:
            return None
        args["raw_input"] = body
    if rule.action == "submit_todo":
        min_len = int(args.pop("min_body_len", 4))
        if len(body) < min_len:
            return None
        args["raw_input"] = body
    return rule.action, args


def try_direct_route(text: str, rules: list[FeishuTriggerRule]) -> tuple[str, dict[str, Any]] | None:
    """Resolve configured triggers, then structural show_answer patterns."""
    resolved = resolve_trigger(text, rules)
    if resolved is not None:
        return resolved

    t = text.strip()
    m = re.match(r"^答案\s*(\d+)\s*$", t, re.IGNORECASE)
    if m:
        return "show_answer", {"question_id": int(m.group(1))}
    if re.match(r"^答案\s*$", t, re.IGNORECASE):
        return "show_answer", {}
    return None
