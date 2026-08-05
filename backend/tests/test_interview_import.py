"""Tests for interview note markdown parser and group packing."""
from pathlib import Path

from app.services.interview_answer_service import build_question_groups
from app.services.interview_note_parser import parse_interview_markdown


def test_parse_interview_markdown_extracts_questions():
    text = """
阿里国际 / Accio
一面：记忆治理
记忆的权威如何定义？
项目是否开源？为什么简历里没有开源地址？

高德
主动取消推进
"""
    items = parse_interview_markdown(text, doc_name="测试面经")
    stems = [i.question_text for i in items]
    assert any("记忆的权威" in s for s in stems)
    assert any("项目是否开源" in s for s in stems)
    assert not any("主动取消" in s for s in stems)
    assert items[0].company == "阿里国际 / Accio"
    assert items[0].group_key == "测试面经::阿里国际 / Accio::一面::记忆治理"
    assert items[0].group_key == items[1].group_key


def test_build_question_groups_keeps_related_together():
    ids = [1, 2, 3, 4, 5]
    keys = {
        1: "doc::阿里::一面",
        2: "doc::阿里::一面",
        3: "doc::阿里::二面",
        4: "doc::高德::一面",
        5: "doc::高德::一面",
    }
    packs = build_question_groups(ids, keys, max_per_pack=10)
    assert packs == [[1, 2], [3], [4, 5]]


def test_build_question_groups_splits_oversized_pack():
    ids = list(range(1, 16))
    keys = {i: "doc::公司::一面" for i in ids}
    packs = build_question_groups(ids, keys, max_per_pack=6)
    assert len(packs) == 3
    assert packs[0] == [1, 2, 3, 4, 5, 6]
    assert packs[1] == [7, 8, 9, 10, 11, 12]
    assert packs[2] == [13, 14, 15]


def test_parse_real_sample_file_if_present():
    path = Path(r"c:\Users\zz34z\Documents\Obsidian Vault\面经\面经一.md")
    if not path.exists():
        return
    items = parse_interview_markdown(path.read_text(encoding="utf-8"), doc_name="面经一")
    assert len(items) >= 50
    # Same company+round questions should share group_key
    by_group: dict[str, int] = {}
    for it in items:
        by_group[it.group_key] = by_group.get(it.group_key, 0) + 1
    assert max(by_group.values()) >= 3
