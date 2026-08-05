"""Prompt template + function binding endpoints (PRD §6.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.prompt import (
    CreateVersionRequest,
    PreviewRenderRequest,
    PreviewRenderResponse,
    PromptTemplateSummary,
    SceneInfo,
    SetCurrentResponse,
    UpdateBindingRequest,
    UpdateVersionRequest,
)
from app.services import prompt_service

router = APIRouter()


@router.get("/scenes", response_model=list[SceneInfo])
def list_scenes(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[SceneInfo]:
    return prompt_service.all_scene_views(
        db,
        tenant_id=ctx.tenant_id,
        schema_cls=SceneInfo,
        summary_cls=PromptTemplateSummary,
    )


@router.get("/versions", response_model=list[PromptTemplateSummary])
def list_versions(
    scene: str = Query(...),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[PromptTemplateSummary]:
    if scene not in prompt_service.SCENE_INFO:
        raise HTTPException(400, detail=f"unknown scene: {scene}")
    rows = prompt_service.list_versions(db, scene, tenant_id=ctx.tenant_id)
    return [PromptTemplateSummary.model_validate(r) for r in rows]


@router.post("/versions", response_model=PromptTemplateSummary, status_code=status.HTTP_201_CREATED)
def create_version(
    payload: CreateVersionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> PromptTemplateSummary:
    try:
        pt = prompt_service.create_version(
            db,
            tenant_id=ctx.tenant_id,
            scene=payload.scene,
            name=payload.name,
            content=payload.content,
            notes=payload.notes,
            set_current=payload.set_current,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return PromptTemplateSummary.model_validate(pt)


@router.patch("/versions/{version_id}", response_model=PromptTemplateSummary)
def update_version(
    version_id: int,
    payload: UpdateVersionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> PromptTemplateSummary:
    try:
        pt = prompt_service.update_notes(
            db, version_id, payload.notes, tenant_id=ctx.tenant_id
        )
    except LookupError:
        raise HTTPException(404, detail="version not found") from None
    db.commit()
    return PromptTemplateSummary.model_validate(pt)


@router.post("/versions/{version_id}/set-current", response_model=SetCurrentResponse)
def set_current(
    version_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> SetCurrentResponse:
    try:
        pt = prompt_service.set_current(db, version_id, tenant_id=ctx.tenant_id)
    except LookupError:
        raise HTTPException(404, detail="version not found") from None
    db.commit()
    return SetCurrentResponse(scene=pt.scene, current_version_id=pt.id)  # type: ignore[arg-type]


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    try:
        prompt_service.delete_version(db, version_id, tenant_id=ctx.tenant_id)
    except LookupError:
        raise HTTPException(404, detail="version not found") from None
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    db.commit()


@router.patch("/bindings/{scene}", response_model=SceneInfo)
def update_binding(
    scene: str,
    payload: UpdateBindingRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> SceneInfo:
    if scene not in prompt_service.SCENE_INFO:
        raise HTTPException(400, detail=f"unknown scene: {scene}")
    prompt_service.update_binding(
        db,
        scene,
        tenant_id=ctx.tenant_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    # Return fresh full view of *only* this scene
    views = prompt_service.all_scene_views(
        db,
        tenant_id=ctx.tenant_id,
        schema_cls=SceneInfo,
        summary_cls=PromptTemplateSummary,
    )
    return next(v for v in views if v.scene == scene)


@router.post("/preview", response_model=PreviewRenderResponse)
def preview(payload: PreviewRenderRequest) -> PreviewRenderResponse:
    rendered, missing, unused = prompt_service.render_preview(
        payload.content, payload.variables
    )
    return PreviewRenderResponse(
        rendered=rendered, missing_placeholders=missing, unused_variables=unused
    )
