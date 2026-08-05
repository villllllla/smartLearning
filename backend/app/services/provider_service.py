"""Provider/Model business logic + connectivity probe.

For ``openai_compatible``: GET ``{base_url}/models`` with Bearer auth.
For ``ollama``: GET ``{base_url}/api/tags`` (no auth).
For ``anthropic``: GET ``{base_url}/v1/models`` with ``x-api-key`` header.
For ``custom``: simple HEAD request on ``base_url`` (best effort).

After the list-models check succeeds, optionally runs a minimal chat completion
on the first enabled model to catch ReadTimeout / proxy issues that only show up
on long generation calls.
"""
from __future__ import annotations

import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import Model, ModelProvider
from app.schemas.provider import ConnectivityResult
from app.services.llm import LLMClient, LLMError, LLMMessage


def _strip(s: str) -> str:
    return s.rstrip("/") if s else s


def _timeout_hint(exc: httpx.HTTPError, *, configured_seconds: int) -> str:
    detail = str(exc).strip() or repr(exc)
    if "timeout" in detail.lower() or "timed out" in detail.lower():
        return (
            f"{detail}（当前生成超时 {configured_seconds}s，可在环境变量 "
            f"SL_MODEL_REQUEST_TIMEOUT_SECONDS 调大；连通性测试的列表接口使用 "
            f"SL_MODEL_PROBE_TIMEOUT_SECONDS）"
        )
    return detail


async def _probe_chat_completion(
    db: Session,
    provider: ModelProvider,
    *,
    timeout: int,
) -> tuple[bool | None, int, str]:
    """Minimal chat round-trip; ``None`` ok means skipped (no enabled model)."""
    model = db.execute(
        select(Model)
        .where(Model.provider_id == provider.id, Model.enabled.is_(True))
        .order_by(Model.is_default.desc(), Model.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if model is None:
        return None, 0, "无已启用模型，跳过生成链路探测"

    probe_timeout = min(90, timeout)

    try:
        client = LLMClient(provider, model, timeout_seconds=probe_timeout)
        t0 = time.perf_counter()
        await client.chat(
            [LLMMessage(role="user", content="Reply with exactly the word: OK")],
            params={"max_tokens": 16, "temperature": 0},
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return (
            True,
            elapsed_ms,
            f"生成探测 OK（{elapsed_ms}ms，模型 {model.name}，探测超时 {probe_timeout}s）",
        )
    except LLMError as exc:
        return False, 0, _timeout_hint(exc, configured_seconds=probe_timeout)
    except httpx.HTTPError as exc:
        return False, 0, _timeout_hint(exc, configured_seconds=probe_timeout)


async def probe_provider(
    db: Session, provider_id: int, *, override_api_key: str | None = None
) -> ConnectivityResult:
    settings = get_settings()
    provider = db.get(ModelProvider, provider_id)
    if provider is None:
        return ConnectivityResult(ok=False, elapsed_ms=0, detail="provider not found")

    api_key = override_api_key or decrypt_secret(provider.api_key_encrypted) or ""
    base = _strip(provider.base_url)
    list_timeout = settings.model_probe_timeout_seconds
    gen_timeout = settings.model_request_timeout_seconds
    headers: dict[str, str] = {}
    url = ""
    discovered: list[str] = []

    try:
        if provider.type == "openai_compatible":
            url = f"{base}/models"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        elif provider.type == "ollama":
            url = f"{base}/api/tags"
        elif provider.type == "anthropic":
            url = f"{base}/v1/models"
            if api_key:
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
        elif provider.type == "custom":
            url = base
        else:
            return ConnectivityResult(
                ok=False,
                elapsed_ms=0,
                detail=f"unknown type: {provider.type}",
                request_timeout_seconds=gen_timeout,
            )

        if not url:
            return ConnectivityResult(
                ok=False,
                elapsed_ms=0,
                detail="base_url 未配置",
                request_timeout_seconds=gen_timeout,
            )

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=list_timeout, trust_env=True) as client:
            method = "HEAD" if provider.type == "custom" else "GET"
            resp = await client.request(method, url, headers=headers)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code >= 400:
            return ConnectivityResult(
                ok=False,
                elapsed_ms=elapsed_ms,
                detail=f"HTTP {resp.status_code}: {resp.text[:200]}",
                request_timeout_seconds=gen_timeout,
            )

        if provider.type == "openai_compatible":
            try:
                data = resp.json().get("data", [])
                discovered = [m.get("id") for m in data if m.get("id")][:50]
            except Exception:  # noqa: BLE001
                pass
        elif provider.type == "ollama":
            try:
                data = resp.json().get("models", [])
                discovered = [m.get("name") for m in data if m.get("name")][:50]
            except Exception:  # noqa: BLE001
                pass
        elif provider.type == "anthropic":
            try:
                data = resp.json().get("data", [])
                discovered = [m.get("id") for m in data if m.get("id")][:50]
            except Exception:  # noqa: BLE001
                pass

        chat_ok, chat_ms, chat_detail = await _probe_chat_completion(
            db, provider, timeout=gen_timeout
        )
        list_detail = f"列表接口 OK（{len(discovered)} models, {elapsed_ms}ms）"
        if chat_ok is False:
            return ConnectivityResult(
                ok=False,
                elapsed_ms=elapsed_ms,
                detail=f"{list_detail}；生成探测失败：{chat_detail}",
                discovered_models=discovered,
                chat_probe_ok=False,
                chat_probe_elapsed_ms=None,
                chat_probe_detail=chat_detail,
                request_timeout_seconds=gen_timeout,
            )

        detail = list_detail
        if chat_detail:
            detail = f"{detail}；{chat_detail}"

        return ConnectivityResult(
            ok=True,
            elapsed_ms=elapsed_ms,
            detail=detail,
            discovered_models=discovered,
            chat_probe_ok=chat_ok,
            chat_probe_elapsed_ms=chat_ms if chat_ok else None,
            chat_probe_detail=chat_detail,
            request_timeout_seconds=gen_timeout,
        )

    except httpx.HTTPError as exc:
        return ConnectivityResult(
            ok=False,
            elapsed_ms=0,
            detail=f"network error: {_timeout_hint(exc, configured_seconds=list_timeout)}",
            request_timeout_seconds=gen_timeout,
        )
