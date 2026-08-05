"""Labelled routing dataset for the Feishu agent.

Each :class:`Case` maps a user utterance to the tool the agent *should* select.
``category`` records which subsystem we expect to resolve it, so the runner can
report per-layer accuracy:

- ``rule_*``   : resolved deterministically without the LLM (fast path). These
                 are scored on every run, no model/API key required.
- ``llm_intent``: no trigger prefix; the LLM intent router must choose the tool.
                 Only scored when a provider is configured (real-LLM mode).
- ``adversarial``: known-hard cases that probe a specific failure mode (e.g.
                 prefix routing swallowing a question that merely starts with
                 "总结"). Reported separately so they don't distort the headline.

Tool vocabulary (must stay in sync with ``agent.AGENT_ACTION_SCHEMA`` and the
trigger rules in ``feishu_trigger_service``):
    draw_questions, show_answer, next_question, reset_chat, chat, help,
    reply_only, get_push_config, update_push_config, push_now, submit_answer,
    submit_learning_note, submit_todo, list_todos, fetch_ai_news
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    text: str
    expected_tool: str
    category: str
    note: str = ""


# --- Deterministic rule fast path (scored on every run) --------------------
RULE_CASES: tuple[Case, ...] = (
    # exact-match triggers
    Case("帮助", "help", "rule_exact"),
    Case("help", "help", "rule_exact"),
    Case("？", "help", "rule_exact"),
    Case("下一题", "next_question", "rule_exact"),
    Case("next", "next_question", "rule_exact"),
    Case("新建对话", "reset_chat", "rule_exact"),
    Case("reset", "reset_chat", "rule_exact"),
    Case("推送设置", "get_push_config", "rule_exact"),
    Case("定时推送", "get_push_config", "rule_exact"),
    Case("立即推题", "push_now", "rule_exact"),
    Case("推题", "push_now", "rule_exact"),
    Case("资讯", "fetch_ai_news", "rule_exact"),
    Case("今日热点", "fetch_ai_news", "rule_exact"),
    Case("ping", "reply_only", "rule_exact", "connectivity probe"),
    Case("连通性测试", "reply_only", "rule_exact", "connectivity probe"),
    Case("待办列表", "list_todos", "rule_exact"),
    Case("我的待办", "list_todos", "rule_exact"),
    Case("todo list", "list_todos", "rule_exact"),
    # structural show_answer regex
    Case("答案 12", "show_answer", "rule_structural", "with question id"),
    Case("答案12", "show_answer", "rule_structural", "no separator"),
    Case("答案", "show_answer", "rule_structural", "current question"),
    # prefix triggers with a body long enough to pass min_body_len
    Case(
        "学习总结 今天复习了 Redis 持久化，RDB 快照与 AOF 追加各有取舍",
        "submit_learning_note",
        "rule_prefix",
    ),
    Case(
        "笔记 学到了 CAP 定理三选二，分区容忍度在分布式系统里不可放弃",
        "submit_learning_note",
        "rule_prefix",
    ),
    Case("待办 明天下午三点提醒我交周报", "submit_todo", "rule_prefix"),
    Case("提醒 周五复习 Redis 主从复制", "submit_todo", "rule_prefix"),
    # answer submissions carrying an explicit question id (parse_answer_submission)
    Case("15 我的答案是二阶段提交，先 prepare 再 commit", "submit_answer", "rule_answer"),
    Case("作答 8 使用布隆过滤器防止缓存穿透", "submit_answer", "rule_answer"),
)


# --- LLM intent routing (scored only with a configured provider) -----------
LLM_CASES: tuple[Case, ...] = (
    Case("来五道 Redis 场景题", "draw_questions", "llm_intent"),
    Case("给我 3 道困难八股", "draw_questions", "llm_intent"),
    Case("随便抽5题练练", "draw_questions", "llm_intent"),
    Case("错题来 5 道", "draw_questions", "llm_intent", "mode=wrong"),
    Case("出两道 MySQL 索引的概念题", "draw_questions", "llm_intent"),
    Case("解释一下 CAP 定理", "chat", "llm_intent"),
    Case("什么是 MVCC？", "chat", "llm_intent"),
    Case("Redis 和 Memcached 有什么区别", "chat", "llm_intent"),
    Case("帮我讲讲 Raft 选主流程", "chat", "llm_intent"),
    # Question-shaped bodies that share a prefix with a note/todo trigger.
    # `resolve_trigger` now detects the question markers and abstains, so
    # these fall through to the LLM intent router like any other `chat` case.
    Case(
        "总结一下 Redis 有哪些数据结构",
        "chat",
        "llm_intent",
        "'总结' prefix must not swallow a question into note-saving",
    ),
    Case(
        "提醒我 CAP 定理是什么",
        "chat",
        "llm_intent",
        "'提醒' prefix vs. an actual question",
    ),
)


# --- Adversarial / known-hard (reported separately) ------------------------
ADVERSARIAL_CASES: tuple[Case, ...] = (
    Case(
        "解释第15题怎么做",
        "chat",
        "adversarial",
        "leading number in a question must not be read as submit_answer",
    ),
)


ALL_CASES: tuple[Case, ...] = RULE_CASES + LLM_CASES + ADVERSARIAL_CASES
