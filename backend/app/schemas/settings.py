"""AppSettings schemas (PRD §6.5)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase

Difficulty = Literal["easy", "medium", "hard"]
QType = Literal["concept", "scenario"]
Theme = Literal["light", "dark", "system"]


class AppSettingsRead(ORMBase):
    practice_default_limit: int
    practice_time_limit_per_question: int | None
    practice_default_difficulties: list[Difficulty]
    practice_default_qtypes: list[QType]
    practice_history_keep_n: int
    appearance_theme: Theme
    appearance_locale: str
    timezone: str
    llm_fallback_model_id: int | None = None


class AppSettingsUpdate(BaseModel):
    practice_default_limit: int | None = Field(None, ge=1, le=50)
    practice_time_limit_per_question: int | None = Field(None, ge=10, le=600)
    practice_default_difficulties: list[Difficulty] | None = None
    practice_default_qtypes: list[QType] | None = None
    practice_history_keep_n: int | None = Field(None, ge=1, le=200)
    appearance_theme: Theme | None = None
    appearance_locale: str | None = None
    timezone: str | None = Field(None, max_length=64)
    llm_fallback_model_id: int | None = None
    clear_llm_fallback_model: bool = False
    # Allow explicit clearing of time limit:
    clear_time_limit: bool = False
