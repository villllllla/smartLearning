"""Provider-specific HTTP adapters.

Each adapter normalises a uniform interface:

    chat(messages, model, params) -> LLMResponse
    chat_stream(messages, model, params) -> AsyncIterator[str]   # text deltas

We intentionally keep "supported" small: openai_compatible covers OpenAI,
DeepSeek, Qwen, Zhipu, Moonshot, etc. ``ollama`` covers local models. Anthropic
is supported in non-stream mode (streaming differs enough to defer).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .types import LLMMessage, LLMResponse, LLMUsage


class LLMHttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def _strip(s: str) -> str:
    return s.rstrip("/") if s else s


def _openai_message(msg: LLMMessage) -> dict:
    """OpenAI Chat Completions message — supports vision via content parts."""
    if not msg.attachments:
        return {"role": msg.role, "content": msg.content}
    parts: list[dict] = [{"type": "text", "text": msg.content}]
    for a in msg.attachments:
        url = a.data_url or a.url
        if url:
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return {"role": msg.role, "content": parts}


# ---------------------------------------------------------------------------
# openai_compatible
# ---------------------------------------------------------------------------


class OpenAICompatibleAdapter:
    type_id = "openai_compatible"

    def __init__(self, base_url: str, api_key: str | None, timeout: int):
        self.base_url = _strip(base_url)
        self.api_key = api_key or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _payload(self, messages: list[LLMMessage], model: str, params: dict) -> dict:
        body: dict = {
            "model": model,
            "messages": [_openai_message(m) for m in messages],
        }
        for k in ("temperature", "top_p", "max_tokens"):
            if params.get(k) is not None:
                body[k] = params[k]
        return body

    async def chat(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
            resp = await client.post(
                url, headers=self._headers(), json=self._payload(messages, model, params)
            )
        if resp.status_code >= 400:
            raise LLMHttpError(resp.status_code, resp.text)
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason"),
        )

    async def chat_stream(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        body = self._payload(messages, model, params)
        body["stream"] = True
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
            async with client.stream(
                "POST", url, headers=self._headers(), json=body
            ) as resp:
                if resp.status_code >= 400:
                    text = await resp.aread()
                    raise LLMHttpError(resp.status_code, text.decode("utf-8", "ignore"))
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        ((evt.get("choices") or [{}])[0]).get("delta") or {}
                    ).get("content")
                    if delta:
                        yield delta


# ---------------------------------------------------------------------------
# ollama
# ---------------------------------------------------------------------------


class OllamaAdapter:
    type_id = "ollama"

    def __init__(self, base_url: str, api_key: str | None, timeout: int):
        # api_key ignored — Ollama is local
        self.base_url = _strip(base_url)
        self.timeout = timeout

    @staticmethod
    def _ollama_message(msg: LLMMessage) -> dict:
        out: dict = {"role": msg.role, "content": msg.content}
        if msg.attachments:
            # Ollama wants base64 (no data: prefix). Caller may pass data_url.
            images: list[str] = []
            for a in msg.attachments:
                if a.data_url and "," in a.data_url:
                    images.append(a.data_url.split(",", 1)[1])
            if images:
                out["images"] = images
        return out

    def _payload(self, messages: list[LLMMessage], model: str, params: dict) -> dict:
        body: dict = {
            "model": model,
            "messages": [self._ollama_message(m) for m in messages],
            "options": {},
        }
        for k in ("temperature", "top_p"):
            if params.get(k) is not None:
                body["options"][k] = params[k]
        if params.get("max_tokens") is not None:
            body["options"]["num_predict"] = params["max_tokens"]
        return body

    async def chat(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> LLMResponse:
        url = f"{self.base_url}/api/chat"
        body = self._payload(messages, model, params)
        body["stream"] = False
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
            resp = await client.post(url, json=body)
        if resp.status_code >= 400:
            raise LLMHttpError(resp.status_code, resp.text)
        data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        return LLMResponse(
            text=text,
            usage=LLMUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0)
                + data.get("eval_count", 0),
            ),
            finish_reason=data.get("done_reason"),
        )

    async def chat_stream(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        body = self._payload(messages, model, params)
        body["stream"] = True
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code >= 400:
                    text = await resp.aread()
                    raise LLMHttpError(resp.status_code, text.decode("utf-8", "ignore"))
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = (evt.get("message") or {}).get("content")
                    if delta:
                        yield delta
                    if evt.get("done"):
                        return


# ---------------------------------------------------------------------------
# anthropic (non-stream only for MVP)
# ---------------------------------------------------------------------------


class AnthropicAdapter:
    type_id = "anthropic"

    def __init__(self, base_url: str, api_key: str | None, timeout: int):
        self.base_url = _strip(base_url)
        self.api_key = api_key or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    @staticmethod
    def _split_system(messages: list[LLMMessage]) -> tuple[str, list[dict]]:
        sys_text = "\n\n".join(m.content for m in messages if m.role == "system")
        non_sys = []
        for m in messages:
            if m.role == "system":
                continue
            if not m.attachments:
                non_sys.append({"role": m.role, "content": m.content})
                continue
            parts: list[dict] = [{"type": "text", "text": m.content}]
            for a in m.attachments:
                if a.data_url and "," in a.data_url:
                    parts.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": a.mime,
                                "data": a.data_url.split(",", 1)[1],
                            },
                        }
                    )
            non_sys.append({"role": m.role, "content": parts})
        return sys_text, non_sys

    async def chat(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> LLMResponse:
        sys_text, msgs = self._split_system(messages)
        body: dict = {
            "model": model,
            "max_tokens": params.get("max_tokens") or 1024,
            "messages": msgs,
        }
        if sys_text:
            body["system"] = sys_text
        for k in ("temperature", "top_p"):
            if params.get(k) is not None:
                body[k] = params[k]
        url = f"{self.base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise LLMHttpError(resp.status_code, resp.text)
        data = resp.json()
        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            usage=LLMUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0),
            ),
            finish_reason=data.get("stop_reason"),
        )

    async def chat_stream(
        self, messages: list[LLMMessage], model: str, params: dict
    ) -> AsyncIterator[str]:
        # Streaming-as-non-stream fallback: emit the full text once.
        resp = await self.chat(messages, model, params)
        if resp.text:
            yield resp.text


def get_adapter(provider_type: str, base_url: str, api_key: str | None, timeout: int):
    if provider_type == "openai_compatible":
        return OpenAICompatibleAdapter(base_url, api_key, timeout)
    if provider_type == "ollama":
        return OllamaAdapter(base_url, api_key, timeout)
    if provider_type == "anthropic":
        return AnthropicAdapter(base_url, api_key, timeout)
    raise ValueError(f"unsupported provider type: {provider_type}")


# Re-exported for convenience in tests
_OPENAI_MESSAGE = _openai_message
