"""Application configuration via pydantic-settings.

Environment variables are prefixed with ``SL_`` to avoid collisions.
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


# Where we persist an auto-generated secret across restarts when
# SL_SECRET_KEY isn't supplied. Without this, every process start would
# rotate the Fernet-derived encryption key and silently invalidate every
# stored provider API key — the user would see them "disappear".
_PERSISTED_SECRET_FILENAME = ".secret_key"

# Placeholder credentials for the auto-created admin. Fine for a local
# single-user run; refused at startup once auth is on (see auth_service
# .ensure_bootstrap_tenant) because they're published in this repo.
DEFAULT_BOOTSTRAP_EMAIL = "admin@local"
DEFAULT_BOOTSTRAP_PASSWORD = "changeme123"


def _load_or_create_secret() -> str:
    """Return a stable secret across restarts in dev.

    Resolution order:
      1. ``SL_SECRET_KEY`` env var (production: always set this).
      2. The cached file ``<data_dir>/.secret_key`` (auto-generated once).
      3. A freshly generated value, written to the cache file for next time.

    Anyone deleting the cache file (or pointing ``SL_DATA_DIR`` elsewhere)
    will, by design, lose access to previously encrypted secrets — that's
    the same threat model as forgetting the env var.
    """
    env_value = os.environ.get("SL_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env_value:
        return env_value

    # Resolve data_dir the same way Settings would, without instantiating
    # Settings (chicken-and-egg: Settings needs the secret factory).
    data_dir = Path(os.environ.get("SL_DATA_DIR", "./data"))
    cache_path = data_dir / _PERSISTED_SECRET_FILENAME

    if cache_path.exists():
        try:
            cached = cache_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            log.warning("could not read cached secret %s: %s", cache_path, exc)
            cached = ""
        if cached:
            return cached

    generated = secrets.token_urlsafe(32)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(generated, encoding="utf-8")
        # Best-effort tighten file perms (no-op on Windows when ACLs apply).
        try:
            os.chmod(cache_path, 0o600)
        except OSError:
            pass
        log.warning(
            "SL_SECRET_KEY not set; generated and persisted a new secret to %s. "
            "Set SL_SECRET_KEY in your environment / .env for production.",
            cache_path,
        )
    except OSError as exc:
        # Last resort: at least the secret survives this single process,
        # which is no worse than the previous behavior.
        log.error(
            "failed to persist auto-generated SECRET_KEY to %s: %s. "
            "Encrypted secrets will be lost on next restart unless you set "
            "SL_SECRET_KEY.",
            cache_path,
            exc,
        )
    return generated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Interactive API docs (/docs, /redoc, /openapi.json). Off by default so a
    # deployment that forgets to set anything doesn't publish its full API map;
    # turn it on in your local .env for development.
    api_docs_enabled: bool = False

    # Read the client address from CF-Connecting-IP / X-Forwarded-For instead of
    # the socket peer. Only enable when a proxy you control (nginx, Cloudflare)
    # is in front and rewrites those headers — otherwise clients can spoof them
    # and bypass rate limiting entirely.
    trust_proxy_headers: bool = False

    # Rate limits, per client IP. See core/rate_limit.py for the threat model.
    rate_limit_enabled: bool = True
    rate_limit_auth_per_window: int = 10
    rate_limit_auth_window_seconds: int = 900
    rate_limit_write_per_window: int = 120
    rate_limit_write_window_seconds: int = 300

    # Storage
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/smartlearning.db"

    # Crypto: source key for the Fernet derivation used to encrypt provider
    # API keys at rest. Resolution: SL_SECRET_KEY env → <data_dir>/.secret_key
    # cache file → newly generated + persisted. Persisting prevents the
    # "API key silently disappears after restart" bug in dev.
    secret_key: str = Field(default_factory=_load_or_create_secret)

    # Practice defaults (PRD §6.4)
    keep_history_per_question: int = 10
    default_question_count_per_wiki: int = 12

    # Model call defaults (LLM chat / JSON generation / embedding)
    model_request_timeout_seconds: int = 180
    # Shorter timeout for GET /models connectivity probe only
    model_probe_timeout_seconds: int = 20

    # Feishu bot (optional IM remote control)
    feishu_bot_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    # Comma-separated Feishu user open_ids allowed to use the bot
    feishu_allowed_open_ids: str = ""

    # When set, machine clients may use X-SL-Token instead of JWT (maps to tenant 1).
    bot_api_token: str = ""

    # Multi-tenant login (JWT). Set false for legacy single-user dev without login.
    auth_enabled: bool = False
    auth_token_expire_hours: int = 168
    auth_allow_register: bool = False
    auth_bootstrap_admin_email: str = DEFAULT_BOOTSTRAP_EMAIL
    auth_bootstrap_admin_password: str = DEFAULT_BOOTSTRAP_PASSWORD

    # Obsidian vault folder sync (watch .md → Wiki main branch)
    obsidian_sync_enabled: bool = False
    obsidian_vault_path: str = ""
    obsidian_sync_debounce_seconds: float = 5.0
    obsidian_sync_on_start: bool = True
    obsidian_sync_dedupe_after: bool = False
    # Comma-separated directory names to skip (in addition to .obsidian, .trash, …)
    obsidian_sync_ignore_dirs: str = ""

    @property
    def obsidian_vault_path_resolved(self) -> Path | None:
        raw = (self.obsidian_vault_path or "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser().resolve()
        return p if p.is_dir() else None

    # Wiki RAG (bge-small-zh + sentence-transformers)
    rag_enabled: bool = True
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    rag_top_k: int = 5
    rag_min_score: float = 0.35
    rag_chunk_max_chars: int = 500
    rag_chunk_overlap: int = 80
    rag_auto_index: bool = True
    rag_default_in_chat: bool = True

    # Question dedupe embeddings (DashScope / OpenAI-compatible or local bge)
    dedupe_use_embedding: bool = False
    dedupe_embedding_threshold: float = 0.92
    embedding_provider: str = "openai_compatible"  # local | openai_compatible
    embedding_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_encoding_format: str = "float"

    # Optional Milvus vector store for question stem search
    milvus_enabled: bool = False
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "sl_questions"
    milvus_metric: str = "L2"  # L2 | COSINE | IP
    milvus_index: str = "IVF_FLAT"
    milvus_index_nlist: int = 128
    milvus_search_nprobe: int = 10

    @property
    def milvus_index_params(self) -> dict:
        return {"nlist": self.milvus_index_nlist}

    @property
    def milvus_search_params(self) -> dict:
        return {"nprobe": self.milvus_search_nprobe}

    @property
    def obsidian_ignore_dir_set(self) -> frozenset[str]:
        extra = {
            x.strip()
            for x in (self.obsidian_sync_ignore_dirs or "").split(",")
            if x.strip()
        }
        return frozenset(extra)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v):  # type: ignore[no-untyped-def]
        return Path(v) if not isinstance(v, Path) else v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def feishu_allowed_open_ids_list(self) -> list[str]:
        return [x.strip() for x in self.feishu_allowed_open_ids.split(",") if x.strip()]

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def wikis_dir(self) -> Path:
        return self.data_dir / "wikis"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.upload_dir, self.wikis_dir, self.attachments_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
