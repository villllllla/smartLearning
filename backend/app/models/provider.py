"""ModelProvider / Model (PRD §6.2.2)."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ModelProvider(Base, TimestampMixin):
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key_encrypted: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    models: Mapped[list["Model"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_provider_tenant_name"),)


class Model(Base, TimestampMixin):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider: Mapped[ModelProvider] = relationship(back_populates="models")

    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_model_provider_name"),
    )
