from app.services.rag.chunking import chunk_markdown


def test_chunk_by_headings():
    md = "# Title\n\nintro\n\n## Redis\n\nredis body\n\n## MySQL\n\nmysql part"
    chunks = chunk_markdown(md, max_chars=40)
    assert len(chunks) >= 2
    assert any("Redis" in c.text or (c.heading and "Redis" in c.heading) for c in chunks)
