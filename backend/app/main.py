"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.auth_middleware import AuthMiddleware
from app.core.config import get_settings
from app.core.rate_limit import RateLimitMiddleware
from app.db.session import SessionLocal
from app.services.auth_service import ensure_bootstrap_tenant
from app.services.push_scheduler import (
    start_interview_answer_scheduler,
    start_push_scheduler,
    stop_interview_answer_scheduler,
    stop_push_scheduler,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Publishing the schema hands an attacker a complete map of the API, so the
    # docs are opt-in (SL_API_DOCS_ENABLED=true) rather than opt-out.
    docs_on = settings.api_docs_enabled
    app = FastAPI(
        title="SmartLearning API",
        version="0.1.0",
        description="智能知识管理与面试训练平台 — 一期 MVP",
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    # Middleware added last runs first. Rate limiting goes outermost so abusive
    # traffic is shed before it reaches auth (and before it can cost LLM spend).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            auth_limit=settings.rate_limit_auth_per_window,
            auth_window_seconds=settings.rate_limit_auth_window_seconds,
            write_limit=settings.rate_limit_write_per_window,
            write_window_seconds=settings.rate_limit_write_window_seconds,
            trust_proxy=settings.trust_proxy_headers,
        )

    if settings.auth_enabled and not settings.trust_proxy_headers:
        log.info(
            "SL_TRUST_PROXY_HEADERS is off — rate limits key on the socket peer. "
            "If a reverse proxy fronts this app, enable it or every request will "
            "share one bucket."
        )

    app.include_router(api_router)

    @app.on_event("startup")
    async def _bootstrap_and_scheduler() -> None:
        db = SessionLocal()
        try:
            ensure_bootstrap_tenant(db, settings)
            db.commit()
        finally:
            db.close()
        start_push_scheduler()
        start_interview_answer_scheduler()

    @app.on_event("shutdown")
    async def _shutdown_scheduler() -> None:
        stop_push_scheduler()
        stop_interview_answer_scheduler()

    @app.get("/")
    def root() -> JSONResponse:
        body = {"name": "SmartLearning", "version": app.version}
        if docs_on:
            body["docs"] = "/docs"
        return JSONResponse(body)

    return app


app = create_app()
