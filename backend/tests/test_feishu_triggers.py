"""Feishu configurable trigger prefix resolution."""
from app.services.feishu_trigger_service import (
    normalize_prefix_list,
    resolve_trigger,
    rules_from_defaults,
    try_direct_route,
)


def test_normalize_prefix_list():
    assert normalize_prefix_list(["总结, 笔记", "总结"]) == ["总结", "笔记"]


def test_resolve_learning_note_prefix():
    rules = rules_from_defaults()
    resolved = resolve_trigger("总结 今天学习了 Redis 持久化机制", rules)
    assert resolved is not None
    tool, args = resolved
    assert tool == "submit_learning_note"
    assert "Redis" in args["raw_input"]


def test_resolve_exact_push_now():
    rules = rules_from_defaults()
    assert resolve_trigger("立即推题", rules) == ("push_now", {})


def test_longest_prefix_wins():
    rules = rules_from_defaults()
    resolved = resolve_trigger("学习总结 今天学了 TCP", rules)
    assert resolved is not None
    assert resolved[0] == "submit_learning_note"
    assert resolved[1]["raw_input"] == "今天学了 TCP"


def test_custom_prefix_from_draft_rules():
    rules = rules_from_defaults()
    note_rule = next(r for r in rules if r.action == "submit_learning_note")
    note_rule.prefixes = ["日报"]
    resolved = resolve_trigger("日报 完成了 wiki 同步功能开发", rules)
    assert resolved is not None
    assert resolved[1]["raw_input"].startswith("完成了 wiki")


def test_try_direct_route_show_answer():
    rules = rules_from_defaults()
    assert try_direct_route("答案 9", rules) == ("show_answer", {"question_id": 9})


# --- question gate: a prefix hit whose body is a question must abstain -----
# Regression guard for the defect the routing eval surfaced: "总结一下 X 有哪些
# 数据结构" starts with the note-taking prefix but is really a question, and was
# being swallowed into submit_learning_note. resolve_trigger now returns None so
# the LLM intent router can classify it as `chat`. These live here (not only in
# eval/routing_cases.py) because the eval only scores them in real-LLM mode.


def test_question_body_abstains_from_note_prefix():
    rules = rules_from_defaults()
    assert resolve_trigger("总结一下 Redis 有哪些数据结构", rules) is None


def test_question_body_abstains_from_todo_prefix():
    rules = rules_from_defaults()
    assert resolve_trigger("提醒我 CAP 定理是什么", rules) is None


def test_question_gate_does_not_block_a_real_note():
    """A statement that merely contains a gated word still saves as a note."""
    rules = rules_from_defaults()
    resolved = resolve_trigger("总结 今天搞清楚了 MVCC 怎么做可见性判断", rules)
    assert resolved is not None
    assert resolved[0] == "submit_learning_note"


def test_explicit_question_mark_abstains_even_in_command_form():
    rules = rules_from_defaults()
    assert resolve_trigger("笔记 Redis 的过期策略是什么？", rules) is None


def test_question_gate_does_not_apply_to_ungated_actions():
    """Only note/todo prefixes are gated — exact commands stay deterministic."""
    rules = rules_from_defaults()
    assert resolve_trigger("推送设置", rules) == ("get_push_config", {})
