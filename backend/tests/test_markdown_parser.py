"""Regression tests for wiki title / metadata extraction."""
from __future__ import annotations

from app.services.markdown_parser import parse_markdown


def test_title_ignores_h1_inside_fenced_code() -> None:
    md = """```bash
# This is a shell comment, not the document title
echo hi
```
# Real document title

Some body.
"""
    meta = parse_markdown(md, "fallback-name")
    assert meta.title == "Real document title"


def test_title_ignores_tilde_fence() -> None:
    md = """~~~python
# not a title
x = 1
~~~
## First section
"""
    meta = parse_markdown(md, "file")
    assert meta.title == "file"


def test_title_after_front_matter_and_code() -> None:
    md = """---
draft: true
---
```yaml
# comment inside yaml block in code fence
foo: bar
```
# Actual title

text
"""
    meta = parse_markdown(md, "fn")
    assert meta.title == "Actual title"


def test_title_without_h1_uses_fallback() -> None:
    md = """Intro paragraph without heading.

```text
# still not title
```
"""
    meta = parse_markdown(md, "my-file")
    assert meta.title == "my-file"
