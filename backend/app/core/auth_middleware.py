"""JWT + optional API token authentication middleware."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.auth_tokens import decode_access_token
from app.core.config import get_settings

_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/integrations/feishu",
)

# Enabling SL_API_DOCS_ENABLED *publishes* the schema: the docs UI is a plain
# browser page that carries no JWT, so gating it behind auth would only break it.
# It is off by default; leave it off on anything reachable from the internet.
_DOCS_PREFIXES = ("/docs", "/openapi.json", "/redoc")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path

        if not settings.auth_enabled:
            request.state.tenant_id = 1
            request.state.user_id = None
            request.state.user_email = None
            request.state.is_service_token = False
            return await call_next(request)

        if path == "/" or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        if settings.api_docs_enabled and path.startswith(_DOCS_PREFIXES):
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        # Machine token (tunnel / scripts) → default tenant
        bot_token = (settings.bot_api_token or "").strip()
        header_token = request.headers.get("X-SL-Token") or ""
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            bearer = auth[7:].strip()
        else:
            bearer = ""

        # User JWT takes precedence: dev proxy may attach X-SL-Token on every request.
        if bearer and (not bot_token or bearer != bot_token):
            payload = decode_access_token(bearer, secret=settings.secret_key)
            if payload is None:
                return JSONResponse(
                    status_code=401, content={"detail": "登录已过期，请重新登录"}
                )
            try:
                request.state.tenant_id = int(payload["tid"])
                request.state.user_id = int(payload["sub"])
                request.state.user_email = str(payload.get("email") or "")
                request.state.is_service_token = False
            except (KeyError, TypeError, ValueError):
                return JSONResponse(status_code=401, content={"detail": "无效的登录凭证"})
            return await call_next(request)

        if bot_token and (header_token == bot_token or bearer == bot_token):
            request.state.tenant_id = 1
            request.state.user_id = None
            request.state.user_email = None
            request.state.is_service_token = True
            return await call_next(request)

        token = bearer or header_token
        if not token:
            return JSONResponse(status_code=401, content={"detail": "请先登录"})

        payload = decode_access_token(token, secret=settings.secret_key)
        if payload is None:
            return JSONResponse(status_code=401, content={"detail": "登录已过期，请重新登录"})

        try:
            request.state.tenant_id = int(payload["tid"])
            request.state.user_id = int(payload["sub"])
            request.state.user_email = str(payload.get("email") or "")
            request.state.is_service_token = False
        except (KeyError, TypeError, ValueError):
            return JSONResponse(status_code=401, content={"detail": "无效的登录凭证"})

        return await call_next(request)
