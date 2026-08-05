"""Parse real interview notes (面经 Markdown) into question stems."""
from __future__ import annotations

import re
from dataclasses import dataclass

_QUESTION_END = re.compile(r"[?？]\s*$")
_ROUND_RE = re.compile(r"([一二三四五六七八九十]+面)")
_SKIP_RE = re.compile(
    r"关注画像|流程备注|按能力|下表|全局信号|候选人感受到|讨论还延伸|"
    r"原始笔记|以下按主题|不属于技术题|岗位选择|定性覆盖|覆盖热度|"
    r"^围绕.+展开的讨论$|^这是通用|^部门聚焦|^主动取消"
)
_COMPANY_HINT = re.compile(
    r"^[\u4e00-\u9fa5A-Za-z0-9]{2,30}(\s*/\s*[\u4e00-\u9fa5A-Za-z0-9]{2,30})?$"
)
_SECTION_HINT = re.compile(
    r"核心|面试问题|讨论|备注|流程|团队|关注画像|主动取消|围绕.+展开"
)


def compute_group_key(
    *,
    doc_name: str = "",
    company: str = "",
    round_label: str = "",
    topic_label: str = "",
    section_label: str = "",
) -> str:
    """Stable key for questions that belong to the same project / interview round."""
    parts = [
        p.strip()
        for p in (doc_name, company, round_label, topic_label, section_label)
        if p and p.strip()
    ]
    return "::".join(parts) or doc_name or "default"


@dataclass
class ParsedInterviewQuestion:
    question_text: str
    company: str = ""
    round_label: str = ""
    topic_label: str = ""
    section_label: str = ""
    source_anchor: str = ""
    group_key: str = ""

    @staticmethod
    def make_group_key(
        *,
        doc_name: str,
        company: str,
        round_label: str,
        topic_label: str,
        section_label: str,
    ) -> str:
        return compute_group_key(
            doc_name=doc_name,
            company=company,
            round_label=round_label,
            topic_label=topic_label,
            section_label=section_label,
        )


def parse_interview_markdown(text: str, *, doc_name: str = "") -> list[ParsedInterviewQuestion]:
    """Extract question lines from Obsidian-style interview notes."""
    company = ""
    round_label = ""
    topic_label = ""
    section_label = ""
    anchor = doc_name
    seen: set[str] = set()
    out: list[ParsedInterviewQuestion] = []

    def _append_question(stem: str) -> None:
        if len(stem) > 400 or stem in seen:
            return
        seen.add(stem)
        gk = ParsedInterviewQuestion.make_group_key(
            doc_name=doc_name,
            company=company,
            round_label=round_label,
            topic_label=topic_label,
            section_label=section_label,
        )
        out.append(
            ParsedInterviewQuestion(
                question_text=stem,
                company=company,
                round_label=round_label,
                topic_label=topic_label,
                section_label=section_label,
                source_anchor=anchor or doc_name,
                group_key=gk,
            )
        )

    for raw in text.splitlines():
        line = raw.strip().lstrip("-*•▪ ").strip()
        if not line or len(line) < 6:
            continue
        if _SKIP_RE.search(line):
            continue
        if line.startswith("|") or line.startswith("```"):
            continue

        if _QUESTION_END.search(line):
            _append_question(line.rstrip())
            continue

        round_m = _ROUND_RE.search(line)
        if round_m and ("：" in line or ":" in line):
            parts = re.split(r"[：:]", line, maxsplit=1)
            round_label = parts[0].strip()[:40]
            topic_label = (parts[1].strip()[:60] if len(parts) > 1 else "") or ""
            section_label = ""
            anchor = f"{company}-{round_label}" if company else round_label
            tail = parts[1].strip() if len(parts) > 1 else ""
            if tail and _QUESTION_END.search(tail):
                _append_question(tail)
            continue

        if (
            not _QUESTION_END.search(line)
            and len(line) <= 28
            and _SECTION_HINT.search(line)
            and "面" not in line[:3]
        ):
            section_label = line[:40]
            continue

        if (
            not _QUESTION_END.search(line)
            and len(line) <= 60
            and ("面" not in line or round_m is None)
            and not line.endswith("。")
            and not line.endswith("；")
        ):
            if _COMPANY_HINT.match(line) or ("/" in line and len(line) < 40):
                company = line[:40]
                anchor = company
                round_label = ""
                topic_label = ""
                section_label = ""

    return out
