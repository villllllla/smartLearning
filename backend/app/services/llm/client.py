"""High-level LLM client + scene resolution.

`LLMClient` wraps a (provider, model) pair plus an adapter and exposes a
uniform ``chat()`` / ``chat_stream()`` / ``chat_json()`` interface.

`resolve_for_scene()` picks the right (PromptTemplate, Model, Provider) for a
given scene by precedence:

1. ``FunctionBinding.model_id`` (if user explicitly bound one)
2. The model marked ``is_default=True``
3. The first ``enabled=True`` model whose Provider is also enabled

On transient upstream failure, optional fallback chain is tried:
``binding.fallback_model_id`` → ``app_settings.llm_fallback_model_id``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import FunctionBinding, Model, ModelProvider, PromptTemplate

from .adapters import LLMHttpError, get_adapter
from .json_repair import ValidationError, parse_json_strict, repair_prompt
from .types import LLMMessage, LLMResponse

log = logging.getLogger(__name__)

# Transient upstream statuses worth retrying (rate limit / overloaded / gateway).
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_BASE_BACKOFF_SECONDS = 1.5


class LLMError(RuntimeError):
    pass


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, LLMHttpError):
        return exc.status in _RETRYABLE_STATUS
    # Network hiccups (timeouts, connection resets) are also worth retrying.
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _overloaded_message(exc: LLMHttpError) -> str:
    if exc.status == 429:
        return "模型调用过于频繁（429），已重试多次仍失败。请稍后再发一次。"
    return (
        f"模型服务暂时繁忙/不可用（HTTP {exc.status}），已自动重试多次仍失败。"
        "这是上游模型的临时波动，请稍后再发一次；如频繁出现可在「设置 → 模型与 Provider」"
        "切换到更稳定的模型。"
    )


@dataclass
class FallbackModelSpec:
    model: Model
    provider: ModelProvider
    params: dict


@dataclass
class ResolvedScene:
    prompt: PromptTemplate
    model: Model
    provider: ModelProvider
    params: dict
    fallback_specs: list[FallbackModelSpec]


def _resolve_enabled_model(
    db: Session, model_id: int, *, tenant_id: int
) -> tuple[Model, ModelProvider] | None:
    model = db.get(Model, model_id)
    if model is None or not model.enabled:
        return None
    provider = db.get(ModelProvider, model.provider_id)
    if (
        provider is None
        or not provider.enabled
        or provider.tenant_id != tenant_id
    ):
        return None
    return model, provider


def _default_model(db: Session, *, tenant_id: int) -> tuple[Model, ModelProvider] | None:
    model = db.execute(
        select(Model)
        .join(ModelProvider, Model.provider_id == ModelProvider.id)
        .where(
            Model.enabled.is_(True),
            ModelProvider.enabled.is_(True),
            ModelProvider.tenant_id == tenant_id,
        )
        .where(Model.is_default.is_(True))
        .order_by(Model.id.asc())
        .limit(1)
    ).scalars().first()
    if model is None:
        model = db.execute(
            select(Model)
            .join(ModelProvider, Model.provider_id == ModelProvider.id)
            .where(
                Model.enabled.is_(True),
                ModelProvider.enabled.is_(True),
                ModelProvider.tenant_id == tenant_id,
            )
            .order_by(Model.id.asc())
            .limit(1)
        ).scalars().first()
    if model is None:
        return None
    provider = db.get(ModelProvider, model.provider_id)
    if provider is None or not provider.enabled:
        return None
    return model, provider


def _build_fallback_specs(
    db: Session,
    *,
    tenant_id: int,
    binding: FunctionBinding,
    primary_model_id: int,
    override_model_id: int | None,
) -> list[FallbackModelSpec]:
    if override_model_id is not None:
        return []
    seen = {primary_model_id}
    specs: list[FallbackModelSpec] = []

    def _append(model_id: int | None, params: dict) -> None:
        if model_id is None or model_id in seen:
            return
        resolved = _resolve_enabled_model(db, model_id, tenant_id=tenant_id)
        if resolved is None:
            return
        model, provider = resolved
        seen.add(model_id)
        specs.append(FallbackModelSpec(model=model, provider=provider, params=params))

    _append(binding.fallback_model_id, dict(binding.fallback_params_json or {}))

    from app.services.settings_service import get_settings_row

    settings = get_settings_row(db, tenant_id)
    _append(settings.llm_fallback_model_id, dict(binding.params_json or {}))

    return specs


def resolve_for_scene(
    db: Session,
    scene: str,
    *,
    tenant_id: int,
    override_model_id: int | None = None,
) -> ResolvedScene:
    """Resolve the (prompt, model, provider) tuple to use for a scene."""
    binding = db.execute(
        select(FunctionBinding).where(
            FunctionBinding.tenant_id == tenant_id,
            FunctionBinding.scene == scene,
        )
    ).scalar_one_or_none()
    if binding is None or binding.prompt_template_id is None:
        raise LLMError(f"scene '{scene}' has no prompt binding configured")

    prompt = db.get(PromptTemplate, binding.prompt_template_id)
    if prompt is None:
        raise LLMError(f"prompt template {binding.prompt_template_id} not found")

    model: Model | None = None
    if override_model_id is not None:
        model = db.get(Model, override_model_id)
    elif binding.model_id is not None:
        model = db.get(Model, binding.model_id)

    if model is None:
        resolved = _default_model(db, tenant_id=tenant_id)
        if resolved is None:
            raise LLMError(
                "没有可用的模型。请到「设置 → 模型与 Provider」启用一个 Provider 并添加模型。"
            )
        model, provider = resolved
    else:
        provider = db.get(ModelProvider, model.provider_id)
        if provider is None or not provider.enabled:
            raise LLMError(
                f"模型 '{model.name}' 所属 Provider 已停用,请到「设置」中启用或选择其它模型。"
            )

    fallback_specs = _build_fallback_specs(
        db,
        tenant_id=tenant_id,
        binding=binding,
        primary_model_id=model.id,
        override_model_id=override_model_id,
    )

    return ResolvedScene(
        prompt=prompt,
        model=model,
        provider=provider,
        params=dict(binding.params_json or {}),
        fallback_specs=fallback_specs,
    )


def _is_fallback_worthy(exc: LLMError) -> bool:
    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, LLMHttpError) and cur.status in _RETRYABLE_STATUS:
            return True
        if isinstance(cur, (httpx.TimeoutException, httpx.TransportError)):
            return True
        cur = cur.__cause__
    return False


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _connection_error_message(provider: ModelProvider, exc: httpx.HTTPError) -> str:
    detail = str(exc).strip() or repr(exc)
    hint = ""
    base = (provider.base_url or "").lower()
    if "googleapis.com" in base or provider.name.lower() == "gemini":
        hint = (
            " 访问 Google API 需本机可直连或配置系统代理；"
            "在启动 uvicorn 前设置环境变量 HTTPS_PROXY=http://127.0.0.1:端口 "
            "（与浏览器/VPN 一致），或在「设置 → 模型与 Provider」改用国内可访问的 Provider。"
        )
    return (
        f"无法连接 Provider「{provider.name}」({provider.base_url}): {detail}.{hint}"
    )


def _require_api_key(provider: ModelProvider, api_key: str | None) -> str | None:
    """Cloud providers must have a non-empty key; local Ollama does not."""
    if provider.type == "ollama":
        return api_key
    if not (api_key or "").strip():
        raise LLMError(
            f"Provider「{provider.name}」未配置 API Key,或密钥无法解密。"
            "请到 Web「设置 → 模型与 Provider」重新填写 API Key 并保存,再点「连通性测试」。"
        )
    return api_key


class LLMClient:
    def __init__(
        self,
        provider: ModelProvider,
        model: Model,
        *,
        params: dict | None = None,
        timeout_seconds: int | None = None,
    ):
        self.provider = provider
        self.model = model
        self.params = params or {}
        timeout = timeout_seconds or get_settings().model_request_timeout_seconds
        api_key = _require_api_key(provider, decrypt_secret(provider.api_key_encrypted))
        self._adapter = get_adapter(
            provider.type,
            provider.base_url,
            api_key,
            timeout,
        )

    @classmethod
    def for_scene(
        cls,
        db: Session,
        scene: str,
        *,
        tenant_id: int,
        override_model_id: int | None = None,
    ) -> tuple["LLMClient", PromptTemplate]:
        scn = resolve_for_scene(
            db, scene, tenant_id=tenant_id, override_model_id=override_model_id
        )
        primary = cls(scn.provider, scn.model, params=scn.params)
        if scn.fallback_specs:
            fallbacks = [
                cls(spec.provider, spec.model, params=spec.params)
                for spec in scn.fallback_specs
            ]
            return FallbackLLMClient(primary, fallbacks), scn.prompt
        return primary, scn.prompt

    async def chat(self, messages: list[LLMMessage], *, params: dict | None = None) -> LLMResponse:
        merged = {**self.params, **(params or {})}
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await self._adapter.chat(messages, self.model.name, merged)
            except LLMHttpError as exc:
                last_exc = exc
                if not _is_transient(exc) or attempt == _MAX_ATTEMPTS:
                    if isinstance(exc, LLMHttpError) and exc.status in _RETRYABLE_STATUS:
                        raise LLMError(_overloaded_message(exc)) from exc
                    raise LLMError(str(exc)) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if not _is_transient(exc) or attempt == _MAX_ATTEMPTS:
                    raise LLMError(_connection_error_message(self.provider, exc)) from exc
            delay = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            log.warning(
                "LLM call transient failure (attempt %s/%s, model=%s): %s; retrying in %.1fs",
                attempt,
                _MAX_ATTEMPTS,
                self.model.name,
                last_exc,
                delay,
            )
            await asyncio.sleep(delay)
        # Unreachable, but keeps type-checkers happy.
        raise LLMError(str(last_exc) if last_exc else "LLM 调用失败")

    async def chat_stream(
        self, messages: list[LLMMessage], *, params: dict | None = None
    ) -> AsyncIterator[str]:
        if not self.model.supports_streaming:
            resp = await self.chat(messages, params=params)
            if resp.text:
                yield resp.text
            return
        merged = {**self.params, **(params or {})}
        try:
            async for delta in self._adapter.chat_stream(messages, self.model.name, merged):
                yield delta
        except LLMHttpError as exc:
            raise LLMError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError(_connection_error_message(self.provider, exc)) from exc

    async def chat_json(
        self,
        messages: list[LLMMessage],
        *,
        schema: dict,
        params: dict | None = None,
    ) -> tuple[Any, LLMResponse]:
        """Call model and parse strict JSON. Retries once with repair prompt on failure."""
        first = await self.chat(messages, params=params)
        try:
            data = parse_json_strict(first.text, schema)
            return data, first
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("LLM JSON parse failed, retrying with repair: %s", exc)
            repair = LLMMessage(
                role="user",
                content=repair_prompt(first.text, schema, str(exc)),
            )
            second = await self.chat(messages + [repair], params=params)
            try:
                data = parse_json_strict(second.text, schema)
            except (json.JSONDecodeError, ValidationError) as exc2:
                raise LLMError(
                    f"模型输出无法被解析为符合 schema 的 JSON: {exc2}\n原始输出片段:\n"
                    f"{second.text[:500]}"
                ) from exc2
            return data, second


class FallbackLLMClient(LLMClient):
    """Primary client with ordered fallback on transient upstream failures."""

    def __init__(self, primary: LLMClient, fallbacks: list[LLMClient]):
        self.provider = primary.provider
        self.model = primary.model
        self.params = primary.params
        self._primary = primary
        self._fallbacks = fallbacks
        self._adapter = primary._adapter

    async def chat(self, messages: list[LLMMessage], *, params: dict | None = None) -> LLMResponse:
        clients = [self._primary, *self._fallbacks]
        last_exc: LLMError | None = None
        for i, client in enumerate(clients):
            try:
                if i > 0:
                    log.warning(
                        "LLM fallback: switching to model=%s (scene retry %s/%s)",
                        client.model.name,
                        i,
                        len(clients) - 1,
                    )
                return await client.chat(messages, params=params)
            except LLMError as exc:
                last_exc = exc
                if i < len(clients) - 1 and _is_fallback_worthy(exc):
                    continue
                raise
        raise last_exc or LLMError("LLM 调用失败")

    async def chat_stream(
        self, messages: list[LLMMessage], *, params: dict | None = None
    ) -> AsyncIterator[str]:
        clients = [self._primary, *self._fallbacks]
        last_exc: LLMError | None = None
        for i, client in enumerate(clients):
            try:
                if i > 0:
                    log.warning(
                        "LLM stream fallback: switching to model=%s",
                        client.model.name,
                    )
                async for delta in client.chat_stream(messages, params=params):
                    yield delta
                return
            except LLMError as exc:
                last_exc = exc
                if i < len(clients) - 1 and _is_fallback_worthy(exc):
                    continue
                raise
        if last_exc:
            raise last_exc

    async def chat_json(
        self,
        messages: list[LLMMessage],
        *,
        schema: dict,
        params: dict | None = None,
    ) -> tuple[Any, LLMResponse]:
        first = await self.chat(messages, params=params)
        try:
            data = parse_json_strict(first.text, schema)
            return data, first
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("LLM JSON parse failed, retrying with repair: %s", exc)
            repair = LLMMessage(
                role="user",
                content=repair_prompt(first.text, schema, str(exc)),
            )
            second = await self.chat(messages + [repair], params=params)
            try:
                data = parse_json_strict(second.text, schema)
            except (json.JSONDecodeError, ValidationError) as exc2:
                raise LLMError(
                    f"模型输出无法被解析为符合 schema 的 JSON: {exc2}\n原始输出片段:\n"
                    f"{second.text[:500]}"
                ) from exc2
            return data, second
