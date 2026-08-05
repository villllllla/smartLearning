"""Unit tests for Feishu command parsing."""
from app.integrations.feishu.commands import parse_command_line


def test_help():
    cmd, tokens = parse_command_line("帮助")
    assert cmd == "帮助"
    assert tokens == []


def test_quiz_with_count_and_filters():
    cmd, tokens = parse_command_line("题目 3 困难 场景")
    assert cmd == "题目"
    assert tokens == ["3", "困难", "场景"]


def test_answer_with_id():
    cmd, tokens = parse_command_line("答案 42")
    assert cmd == "答案"
    assert tokens == ["42"]


def test_chat_prefix():
    cmd, tokens = parse_command_line("对话解释CAP定理")
    assert cmd == "对话"
    assert "解释CAP定理" in " ".join(tokens) or tokens == ["解释CAP定理"]


def test_tag_in_quiz():
    cmd, tokens = parse_command_line("题目 5 标签:Redis,网络")
    assert cmd == "题目"
    assert any("标签" in t for t in tokens)


def test_direct_route_help():
    from app.services.feishu_trigger_service import rules_from_defaults, try_direct_route

    rules = rules_from_defaults()
    assert try_direct_route("帮助", rules) == ("help", {})
    assert try_direct_route("答案 12", rules) == ("show_answer", {"question_id": 12})
    assert try_direct_route("立即推题", rules) == ("push_now", {})
    assert try_direct_route("测试连接", rules)[0] == "reply_only"
    assert try_direct_route("测试连通性", rules)[0] == "reply_only"
