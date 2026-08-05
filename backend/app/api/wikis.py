"""Wiki endpoints (PRD §6.1.5)."""
from __future__ import annotations

import io
import mimetypes
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.wiki import (
    BranchSummary,
    UploadResponse,
    UploadResultItem,
    WikiDetail,
    WikiSummary,
)
from app.services.branch_service import BranchError, get_branch, head_content
from app.services.markdown_parser import parse_markdown
from app.services.wiki_import import import_zip
from app.services.wiki_service import (
    bulk_create_from_uploads,
    get_wiki,
    list_wikis,
    soft_delete_wiki,
)

router = APIRouter()


def _slugify(text: str, fallback: str = "untitled") -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text or "", flags=re.UNICODE).strip("-")
    return s or fallback


def _content_disposition(filename: str) -> str:
    ascii_fallback = re.sub(r"[^\w.-]+", "_", filename) or "download"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


_ALLOWED_MD_EXT = (".md", ".markdown")
_ALLOWED_ZIP_EXT = (".zip",)
_ALLOWED_EXT = _ALLOWED_MD_EXT + _ALLOWED_ZIP_EXT


@router.post("/upload", response_model=UploadResponse)
async def upload_wikis(
    files: list[UploadFile] = File(
        ...,
        description=(
            "多个 .md / .markdown 文件;或 .zip(含 .md + 同目录图片，"
            "会自动改写为可服务的链接)"
        ),
    ),
    collection_id: int | None = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> UploadResponse:
    """Multi-file upload (PRD §6.1.3 / US-01).

    Accepts:
      - One or more bare ``.md`` / ``.markdown`` files (legacy path).
      - One or more ``.zip`` bundles; for each zip we run
        ``wiki_import.import_zip`` which extracts referenced local assets and
        rewrites the markdown to point at ``/api/wiki/{wiki_id}/assets/{path}``.
    """
    md_parsed: list[tuple[str, str]] = []  # (filename, content) for plain MD
    zip_blobs: list[tuple[str, bytes]] = []  # (filename, data) for zips
    rejected: list[UploadResultItem] = []

    for f in files:
        name = f.filename or "untitled.md"
        lower = name.lower()
        if lower.endswith(_ALLOWED_ZIP_EXT):
            zip_blobs.append((name, await f.read()))
            continue
        if not lower.endswith(_ALLOWED_MD_EXT):
            rejected.append(
                UploadResultItem(
                    filename=name,
                    success=False,
                    error="仅支持 .md / .markdown / .zip 文件",
                )
            )
            continue
        try:
            raw = await f.read()
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            rejected.append(
                UploadResultItem(filename=name, success=False, error="文件不是 UTF-8 编码")
            )
            continue
        md_parsed.append((name, content))

    outcomes = bulk_create_from_uploads(db, md_parsed, tenant_id=ctx.tenant_id)
    results: list[UploadResultItem] = []
    created_count = 0
    failed_count = 0
    for o in outcomes:
        if o["wiki"] is not None:
            wiki = o["wiki"]
            created_count += 1
            results.append(
                UploadResultItem(
                    filename=o["filename"],
                    success=True,
                    wiki_id=wiki.id,
                    title=wiki.title,
                )
            )
        else:
            failed_count += 1
            results.append(
                UploadResultItem(
                    filename=o["filename"], success=False, error=o["error"]
                )
            )

    # Zip bundles run after plain mds — they may produce multiple wikis each.
    for arch_name, blob in zip_blobs:
        zip_results = import_zip(
            db, archive_filename=arch_name, data=blob, tenant_id=ctx.tenant_id
        )
        for r in zip_results:
            if r.wiki is not None:
                created_count += 1
                note = f"来自 {arch_name}"
                if r.assets_written:
                    note += f" · 提取 {r.assets_written} 个资产"
                if r.missing_refs:
                    note += f" · {len(r.missing_refs)} 条引用未匹配"
                results.append(
                    UploadResultItem(
                        filename=r.filename,
                        success=True,
                        wiki_id=r.wiki.id,
                        title=r.wiki.title,
                        error=note if r.missing_refs else None,
                    )
                )
            else:
                failed_count += 1
                results.append(
                    UploadResultItem(
                        filename=r.filename, success=False, error=r.error or "导入失败"
                    )
                )

    db.commit()
    failed_count += len(rejected)
    results.extend(rejected)

    return UploadResponse(
        created=created_count,
        failed=failed_count,
        results=results,
    )


@router.get("", response_model=Page[WikiSummary])
def list_wikis_endpoint(
    q: str | None = Query(None, description="模糊搜索:标题或正文"),
    collection_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> Page[WikiSummary]:
    items, total = list_wikis(
        db,
        tenant_id=ctx.tenant_id,
        q=q,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )
    from app.services.wiki_generation_service import wiki_generation_stats

    stats = wiki_generation_stats(db, [w.id for w in items])
    summaries: list[WikiSummary] = []
    for w in items:
        s = stats.get(w.id, {})
        summaries.append(
            WikiSummary(
                id=w.id,
                title=w.title,
                collection_id=w.collection_id,
                current_main_commit_id=w.current_main_commit_id,
                word_count=w.word_count,
                excerpt=w.excerpt,
                updated_at=w.updated_at,
                created_at=w.created_at,
                bank_question_count=s.get("bank_question_count", 0),
                pending_candidate_count=s.get("pending_candidate_count", 0),
                pending_candidate_total=s.get("pending_candidate_total", 0),
                pending_batch_count=s.get("pending_batch_count", 0),
                pending_batch_id=s.get("pending_batch_id"),
            )
        )
    return Page[WikiSummary](
        items=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{wiki_id}", response_model=WikiDetail)
def get_wiki_endpoint(
    wiki_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> WikiDetail:
    wiki = get_wiki(db, wiki_id, tenant_id=ctx.tenant_id)
    if wiki is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="wiki not found")

    from app.services.wiki_generation_service import wiki_generation_stats

    content_md = wiki.current_main_commit.content_md if wiki.current_main_commit else ""
    meta = parse_markdown(content_md, fallback_title=wiki.title)
    s = wiki_generation_stats(db, [wiki.id]).get(wiki.id, {})
    return WikiDetail(
        id=wiki.id,
        title=wiki.title,
        collection_id=wiki.collection_id,
        word_count=wiki.word_count,
        excerpt=wiki.excerpt,
        updated_at=wiki.updated_at,
        created_at=wiki.created_at,
        bank_question_count=s.get("bank_question_count", 0),
        pending_candidate_count=s.get("pending_candidate_count", 0),
        pending_candidate_total=s.get("pending_candidate_total", 0),
        pending_batch_count=s.get("pending_batch_count", 0),
        pending_batch_id=s.get("pending_batch_id"),
        current_main_commit_id=wiki.current_main_commit_id,
        content_md=content_md,
        toc=[{"level": t["level"], "text": t["text"], "anchor": t["anchor"]} for t in meta.toc],
        branches=[BranchSummary.model_validate(b) for b in wiki.branches],
    )


@router.delete("/{wiki_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wiki_endpoint(
    wiki_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    if not soft_delete_wiki(db, wiki_id, tenant_id=ctx.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="wiki not found")
    db.commit()


@router.get("/{wiki_id}/download")
def download_wiki(
    wiki_id: int,
    branch_id: int | None = Query(
        None, description="下载指定分支 HEAD；默认 main 当前内容"
    ),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Download wiki markdown. Bundles ``_assets`` into a zip when present."""
    wiki = get_wiki(db, wiki_id, tenant_id=ctx.tenant_id)
    if wiki is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="wiki not found")

    if branch_id is not None:
        try:
            branch = get_branch(db, branch_id)
        except BranchError as exc:
            raise HTTPException(exc.http_status, detail=exc.args[0]) from exc
        if branch.wiki_id != wiki_id:
            raise HTTPException(400, detail="branch does not belong to this wiki")
        content_md = head_content(branch, db)
    else:
        content_md = (
            wiki.current_main_commit.content_md if wiki.current_main_commit else ""
        )

    settings = get_settings()
    slug = _slugify(wiki.title)
    md_name = f"{slug}-{wiki.id}.md"
    assets_root = (settings.wikis_dir / str(wiki_id) / "_assets").resolve()
    has_assets = assets_root.is_dir() and any(assets_root.rglob("*"))

    if has_assets:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(md_name, content_md)
            for path in assets_root.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(assets_root).as_posix()
                    zf.write(path, f"assets/{rel}")
        buf.seek(0)
        zip_name = f"{slug}-{wiki.id}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": _content_disposition(zip_name)},
        )

    return Response(
        content=content_md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(md_name)},
    )


@router.get(
    "/{wiki_id}/assets/{asset_path:path}",
    include_in_schema=False,  # static asset, not part of REST contract
)
def serve_asset(wiki_id: int, asset_path: str) -> FileResponse:
    """Serve an extracted zip asset for the given wiki.

    Path traversal defense: we resolve the candidate path under the wiki's
    ``_assets`` directory and reject anything that escapes it. Anonymous
    access is fine in this single-user MVP; flip to require-auth once the
    multi-user phase lands.
    """
    settings = get_settings()
    root = (settings.wikis_dir / str(wiki_id) / "_assets").resolve()
    if not root.exists():
        raise HTTPException(404, detail="asset not found")

    # Reject obviously malicious tokens before we even touch the filesystem.
    if any(seg in ("..", "") for seg in asset_path.replace("\\", "/").split("/")):
        raise HTTPException(400, detail="invalid asset path")

    candidate = (root / asset_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(400, detail="invalid asset path") from exc
    if not candidate.is_file():
        raise HTTPException(404, detail="asset not found")

    mime, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(
        Path(candidate),
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=3600"},
    )
