"""Zip import for wikis (PRD §6.1.3 extended).

A typical export from Obsidian / Typora / VS Code looks like:

    note.zip
      ├── note.md
      └── assets/
          ├── pic1.png
          └── pic2.jpg

…or, when no folder structure:

    note.zip
      ├── note.md
      ├── note-1.png
      └── note-2.png

This module:

1. Walks the zip and collects every ``.md`` / ``.markdown`` entry — each
   produces one wiki, located at its own folder inside the archive.
2. For each markdown, parses out **local relative references** in the
   common Markdown link / image syntax plus raw ``<img src="...">``,
   resolves them relative to the markdown's own folder, and pulls the
   matching files out of the zip.
3. Writes the extracted assets under
   ``<wikis_dir>/<wiki_id>/_assets/<resolved-path>`` and rewrites every
   matched reference in the markdown to
   ``/api/wiki/<wiki_id>/assets/<resolved-path>`` — a stable URL served
   by ``app.api.wikis.serve_asset``.
4. Missing references (path that has no matching zip entry) are left as-is
   so the user can still see what was meant; we surface the count via
   ``WikiImportResult.missing_refs``.

Safety:
- We reject any zip entry whose normalized path escapes the archive root
  (``..`` segments collapsing to a prefix outside) — classic "zip slip".
- We never write outside ``<wikis_dir>/<wiki_id>/_assets/``.
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Wiki
from app.services.wiki_service import create_wiki_from_markdown

_MD_EXT = (".md", ".markdown")


# Inline image: ![alt](url "title")  -- title optional, url no spaces unless quoted
_IMG_INLINE = re.compile(
    r"(?P<bang>!)\[(?P<alt>[^\]]*)\]\((?P<lead>\s*)(?P<url><[^>]+>|[^)\s]+)(?P<rest>(?:\s+\"[^\"]*\")?\s*)\)",
)
# Inline link: [text](url "title")
_LINK_INLINE = re.compile(
    r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<lead>\s*)(?P<url><[^>]+>|[^)\s]+)(?P<rest>(?:\s+\"[^\"]*\")?\s*)\)",
)
# Reference-style definition: [id]: url "title"
_REF_DEF = re.compile(
    r"^(?P<prefix>\s*\[(?P<id>[^\]]+)\]:\s*)(?P<url><[^>]+>|\S+)(?P<rest>.*)$",
    re.MULTILINE,
)
# Raw HTML <img src="..."> / <img src='...'>
_HTML_IMG = re.compile(
    r"(<img\b[^>]*\bsrc\s*=\s*)(?P<quote>[\"'])(?P<url>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)


@dataclass
class WikiImportResult:
    filename: str
    wiki: Wiki | None
    error: str | None = None
    assets_written: int = 0
    missing_refs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _looks_local(url: str) -> bool:
    """Is ``url`` something we should attempt to resolve inside the zip?

    Excludes: absolute URLs (with scheme), root-anchored paths, anchors,
    mailto/tel, data URLs.
    """
    s = url.strip()
    if not s or s.startswith("#"):
        return False
    if s.startswith(("/", "\\")):
        return False
    if s.startswith(("data:", "mailto:", "tel:", "javascript:")):
        return False
    parts = urlsplit(s)
    if parts.scheme:  # http / https / ftp / etc.
        return False
    return True


def _strip_angle(url: str) -> tuple[str, bool]:
    """Markdown allows ``<url>`` angled form to permit spaces. Returns (inner, was_angled)."""
    s = url.strip()
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1], True
    return s, False


def _safe_join(base_dir: str, ref: str) -> str | None:
    """Resolve ``ref`` relative to ``base_dir`` (both posix paths), normalize,
    and return None if the result escapes the archive root (starts with ``..``)
    or is absolute."""
    raw = unquote(ref)
    # Drop any fragment / query on the reference
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw:
        return None
    if raw.startswith(("/", "\\")):
        return None
    # Normalize on posix sep; tolerate input separators
    raw = raw.replace("\\", "/")
    combined = posixpath.normpath(posixpath.join(base_dir, raw))
    if combined.startswith("../") or combined == "..":
        return None
    if posixpath.isabs(combined):
        return None
    return combined


def _decode_zip_name(zi: zipfile.ZipInfo) -> str:
    """Best-effort decode zip entry name.

    If the entry's filename was stored as cp437 (no UTF-8 flag), try a few
    fallbacks. UTF-8 entries are returned as-is.
    """
    if zi.flag_bits & 0x800:
        return zi.filename
    # Re-encode raw bytes then try decodings commonly seen on Windows-zh
    raw = zi.filename.encode("cp437", errors="replace")
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return zi.filename


def _iter_zip_safe(zf: zipfile.ZipFile) -> Iterable[tuple[str, zipfile.ZipInfo]]:
    """Yield (normalized_name, ZipInfo) for safe entries only (no zip-slip)."""
    for zi in zf.infolist():
        if zi.is_dir():
            continue
        name = _decode_zip_name(zi)
        norm = posixpath.normpath(name.replace("\\", "/"))
        if norm.startswith(("../", "/")) or norm == "..":
            continue
        yield norm, zi


def _rewrite_refs(
    md_text: str, base_dir: str, name_lookup: dict[str, str]
) -> tuple[str, set[str], list[str]]:
    """Rewrite local relative refs that exist in ``name_lookup``.

    ``name_lookup`` maps **lowercased** archive-relative paths to their real
    name (so we can also match Windows-friendly case-insensitive references).
    Returns (new_md, used_real_names, missing_refs).
    """
    used: set[str] = set()
    missing: list[str] = []

    def _process(url_raw: str) -> str | None:
        inner, was_angled = _strip_angle(url_raw)
        if not _looks_local(inner):
            return None
        resolved = _safe_join(base_dir, inner)
        if resolved is None:
            # Local ref the user clearly wrote, but it escapes the archive
            # or is otherwise unsafe — log so the import result can surface it.
            missing.append(inner.strip())
            return None
        real = name_lookup.get(resolved.lower())
        if real is None:
            missing.append(resolved)
            return None
        used.add(real)
        # Quote sparingly: only encode space; preserve the rest for readability
        rewritten_path = real.replace(" ", "%20")
        new_url = f"__SL_ASSET__/{rewritten_path}"
        return f"<{new_url}>" if was_angled else new_url

    def _sub_inline(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        if "alt" in match.groupdict():
            return (
                f"{match.group('bang')}[{match.group('alt')}]"
                f"({match.group('lead')}{new}{match.group('rest')})"
            )
        return (
            f"[{match.group('text')}]"
            f"({match.group('lead')}{new}{match.group('rest')})"
        )

    def _sub_ref(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        return f"{match.group('prefix')}{new}{match.group('rest')}"

    def _sub_html(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        # If new came back angled (rare for html), strip the brackets
        if new.startswith("<") and new.endswith(">"):
            new = new[1:-1]
        return f"{match.group(1)}{match.group('quote')}{new}{match.group('quote')}"

    rewritten = _IMG_INLINE.sub(_sub_inline, md_text)
    rewritten = _LINK_INLINE.sub(_sub_inline, rewritten)
    rewritten = _REF_DEF.sub(_sub_ref, rewritten)
    rewritten = _HTML_IMG.sub(_sub_html, rewritten)
    return rewritten, used, missing


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def import_zip(
    db: Session, *, archive_filename: str, data: bytes, tenant_id: int
) -> list[WikiImportResult]:
    """Top-level: import every .md found inside the zip blob.

    Returns one ``WikiImportResult`` per markdown encountered; if the zip
    contains zero markdowns, returns a single failed result so the caller
    can surface the error to the user.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        return [WikiImportResult(filename=archive_filename, wiki=None, error=f"无效 zip: {exc}")]

    entries: dict[str, zipfile.ZipInfo] = {}
    for norm, zi in _iter_zip_safe(zf):
        entries[norm] = zi

    md_paths = [p for p in entries if p.lower().endswith(_MD_EXT)]
    if not md_paths:
        return [
            WikiImportResult(
                filename=archive_filename,
                wiki=None,
                error="zip 中未找到 .md / .markdown 文件",
            )
        ]

    # Sort so iteration is deterministic (shallowest first → top-level mds win)
    md_paths.sort(key=lambda p: (p.count("/"), p.lower()))

    # Lowercase index of every zip entry — used for case-insensitive matching.
    name_lookup_lower = {p.lower(): p for p in entries}

    results: list[WikiImportResult] = []
    for md_path in md_paths:
        try:
            base_dir = posixpath.dirname(md_path)
            md_bytes = zf.read(entries[md_path])
            try:
                md_text = md_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try GBK as a fallback for Windows-zh exports
                md_text = md_bytes.decode("gbk", errors="replace")

            rewritten, used_assets, missing = _rewrite_refs(
                md_text, base_dir, name_lookup_lower
            )

            # Create the wiki with the rewritten markdown, but with a sentinel
            # placeholder for the eventual asset URL prefix. The wiki id is only
            # known after the row is flushed, so we substitute *after* creation.
            display_name = posixpath.basename(md_path)
            wiki = create_wiki_from_markdown(
                db, tenant_id=tenant_id, filename=display_name, content_md=rewritten
            )
            # Now patch the sentinel with the real asset URL prefix.
            real_prefix = f"/api/wiki/{wiki.id}/assets"
            final_md = wiki.current_main_commit.content_md.replace(
                "__SL_ASSET__", real_prefix
            )
            if final_md != wiki.current_main_commit.content_md:
                wiki.current_main_commit.content_md = final_md
                # Hash & meta don't need to be perfectly accurate here — the
                # initial-commit hash is informational; we refresh excerpt too.
                from app.services.markdown_parser import parse_markdown

                meta = parse_markdown(final_md, fallback_title=wiki.title)
                wiki.title = meta.title or wiki.title
                wiki.word_count = meta.word_count
                wiki.excerpt = meta.excerpt
                wiki.current_main_commit.content_hash = meta.content_hash
                db.flush()

            # Extract the referenced assets to data/wikis/<wiki_id>/_assets/
            settings = get_settings()
            asset_root = settings.wikis_dir / str(wiki.id) / "_assets"
            asset_root.mkdir(parents=True, exist_ok=True)
            written = 0
            for real_name in used_assets:
                target = asset_root / real_name
                # Defense in depth: ensure target resolves under asset_root
                try:
                    target_resolved = target.resolve()
                    asset_root_resolved = asset_root.resolve()
                    if asset_root_resolved not in target_resolved.parents:
                        continue
                except OSError:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entries[real_name]) as src, target.open("wb") as dst:
                    dst.write(src.read())
                written += 1

            results.append(
                WikiImportResult(
                    filename=display_name,
                    wiki=wiki,
                    assets_written=written,
                    missing_refs=missing,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                WikiImportResult(
                    filename=md_path, wiki=None, error=str(exc)
                )
            )

    return results
