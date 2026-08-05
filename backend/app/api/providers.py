"""Provider & Model endpoints (PRD §6.2.2 / §6.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.core.security import decrypt_secret, encrypt_secret, mask_key
from app.db.session import get_db
from app.models import Model, ModelProvider
from app.schemas.provider import (
    PROVIDER_TYPES,
    ConnectivityResult,
    ModelCreate,
    ModelSummary,
    ModelUpdate,
    ProviderCreate,
    ProviderSummary,
    ProviderUpdate,
)
from app.services.provider_service import probe_provider

router = APIRouter()


def _to_summary(p: ModelProvider) -> ProviderSummary:
    plain_key = decrypt_secret(p.api_key_encrypted)
    return ProviderSummary(
        id=p.id,
        name=p.name,
        type=p.type,
        base_url=p.base_url,
        enabled=p.enabled,
        has_api_key=bool(plain_key),
        masked_api_key=mask_key(plain_key),
        created_at=p.created_at,
        models=[ModelSummary.model_validate(m) for m in p.models],
    )


@router.get("/types", response_model=list[str])
def list_provider_types() -> list[str]:
    return list(PROVIDER_TYPES)


@router.get("", response_model=list[ProviderSummary])
def list_providers(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[ProviderSummary]:
    rows = (
        db.query(ModelProvider)
        .filter(ModelProvider.tenant_id == ctx.tenant_id)
        .order_by(ModelProvider.id.asc())
        .all()
    )
    return [_to_summary(p) for p in rows]


@router.post("", response_model=ProviderSummary, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ProviderSummary:
    if payload.type not in PROVIDER_TYPES:
        raise HTTPException(400, detail=f"type must be one of {PROVIDER_TYPES}")
    if (
        db.query(ModelProvider)
        .filter(ModelProvider.tenant_id == ctx.tenant_id, ModelProvider.name == payload.name)
        .first()
    ):
        raise HTTPException(409, detail="provider name already exists")
    p = ModelProvider(
        tenant_id=ctx.tenant_id,
        name=payload.name,
        type=payload.type,
        base_url=payload.base_url,
        api_key_encrypted=encrypt_secret(payload.api_key),
        enabled=payload.enabled,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_summary(p)


@router.patch("/{provider_id}", response_model=ProviderSummary)
def update_provider(
    provider_id: int,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ProviderSummary:
    p = db.get(ModelProvider, provider_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")

    if payload.name is not None:
        p.name = payload.name
    if payload.type is not None:
        if payload.type not in PROVIDER_TYPES:
            raise HTTPException(400, detail=f"type must be one of {PROVIDER_TYPES}")
        p.type = payload.type
    if payload.base_url is not None:
        p.base_url = payload.base_url
    if payload.enabled is not None:
        p.enabled = payload.enabled

    # api_key semantics: undefined → keep, "" → keep, null → clear, value → replace
    if "api_key" in payload.model_fields_set:
        if payload.api_key is None:
            p.api_key_encrypted = None
        elif payload.api_key != "":
            p.api_key_encrypted = encrypt_secret(payload.api_key)

    db.commit()
    db.refresh(p)
    return _to_summary(p)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    p = db.get(ModelProvider, provider_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")
    db.delete(p)
    db.commit()


@router.post("/{provider_id}/probe", response_model=ConnectivityResult)
async def probe_provider_endpoint(
    provider_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ConnectivityResult:
    p = db.get(ModelProvider, provider_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")
    return await probe_provider(db, provider_id)


# ---- Models -----------------------------------------------------------------


@router.post(
    "/{provider_id}/models",
    response_model=ModelSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_model(
    provider_id: int,
    payload: ModelCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ModelSummary:
    prov = db.get(ModelProvider, provider_id)
    if prov is None or prov.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")
    if db.query(Model).filter(Model.provider_id == provider_id, Model.name == payload.name).first():
        raise HTTPException(409, detail="model already exists for this provider")
    m = Model(
        provider_id=provider_id,
        name=payload.name,
        supports_vision=payload.supports_vision,
        supports_streaming=payload.supports_streaming,
        context_window=payload.context_window,
        is_default=payload.is_default,
        enabled=payload.enabled,
    )
    if payload.is_default:
        db.query(Model).filter(Model.id != m.id).update({Model.is_default: False})
    db.add(m)
    db.commit()
    db.refresh(m)
    return ModelSummary.model_validate(m)


@router.patch("/{provider_id}/models/{model_id}", response_model=ModelSummary)
def update_model(
    provider_id: int,
    model_id: int,
    payload: ModelUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ModelSummary:
    prov = db.get(ModelProvider, provider_id)
    if prov is None or prov.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")
    m = db.get(Model, model_id)
    if m is None or m.provider_id != provider_id:
        raise HTTPException(404, detail="model not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    if payload.is_default:
        db.query(Model).filter(Model.id != m.id).update({Model.is_default: False})
    db.commit()
    db.refresh(m)
    return ModelSummary.model_validate(m)


@router.delete(
    "/{provider_id}/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_model(
    provider_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    prov = db.get(ModelProvider, provider_id)
    if prov is None or prov.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="provider not found")
    m = db.get(Model, model_id)
    if m is None or m.provider_id != provider_id:
        raise HTTPException(404, detail="model not found")
    db.delete(m)
    db.commit()
