"""Optional API token guard when exposing SmartLearning via a tunnel."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

# Paths that stay open without X-SL-Token (Feishu webhook + health/docs).
_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/integrations/feishu",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class BotApiTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        token = (settings.bot_api_token or "").strip()
        if not token:
            return await call_next(request)

        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        header = request.headers.get("X-SL-Token") or ""
        if not header and request.headers.get("Authorization", "").startswith("Bearer "):
            header = request.headers["Authorization"][7:].strip()

        if header != token:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid X-SL-Token"},
            )
        return await call_next(request)
