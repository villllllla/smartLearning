"""Strict JSON parsing with one self-repair attempt (PRD §11)."""
from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import Draft7Validator, ValidationError

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_codeblock(text: str) -> str:
    """Best-effort: drop surrounding ```json fences.

    The model is *instructed* not to use fences, but reality is messy.
    """
    return _FENCE_RE.sub("", text.strip()).strip()


def _extract_first_json(text: str) -> str | None:
    """Scan for the first balanced ``{...}`` or ``[...]`` segment."""
    text = text.strip()
    if not text:
        return None
    # Quick path: full text is already JSON-ish
    for opener, closer in (("{", "}"), ("[", "]")):
        i = text.find(opener)
        if i < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(i, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
    return None


def parse_json_strict(raw: str, schema: dict | None = None) -> Any:
    """Parse ``raw`` to JSON, optionally validate. Raises on failure."""
    text = _strip_codeblock(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        candidate = _extract_first_json(text)
        if candidate is None:
            raise
        data = json.loads(candidate)
    if schema is not None:
        Draft7Validator(schema).validate(data)
    return data


def repair_prompt(original: str, schema: dict, last_error: str) -> str:
    """Build a follow-up message instructing the model to fix its own output."""
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "你上一条回复无法被解析为合法 JSON,或不满足 schema。请仅输出修复后的 JSON,"
        "不要包含任何额外文字、不要使用 markdown 代码块包裹。\n\n"
        f"[校验错误]\n{last_error}\n\n"
        f"[必须遵守的 JSON Schema]\n{schema_str}\n\n"
        f"[你上一条原始输出]\n{original}\n"
    )


__all__ = ["parse_json_strict", "repair_prompt", "ValidationError"]
