"""Prompt template / function binding API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase

SceneLiteral = Literal[
    "chat_general",
    "wiki_to_questions",
    "answer_scoring",
    "wiki_summary",
    "learning_note_structuring",
    "todo_intent_parsing",
    "ai_news_curation",
    "plan_decomposition",
    "todo_motivation",
    "interview_answer_generation",
]


class PromptTemplateSummary(ORMBase):
    id: int
    name: str
    scene: str
    content: str
    version_no: int
    is_current: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class SceneInfo(BaseModel):
    """One row per scene — describes its meaning + which placeholders are required."""

    scene: SceneLiteral
    title: str
    description: str
    placeholders: list[str] = Field(
        default_factory=list,
        description="模板中应当出现的占位符,如 {QUESTION}/{N}/{MARKDOWN}",
    )
    binding_model_id: int | None = None
    binding_model_name: str | None = None
    binding_provider_name: str | None = None
    binding_fallback_model_id: int | None = None
    binding_fallback_model_name: str | None = None
    binding_fallback_provider_name: str | None = None
    binding_params: dict = Field(default_factory=dict)
    binding_fallback_params: dict = Field(default_factory=dict)
    model_tier: str | None = Field(
        None, description="fast = 建议小模型; capable = 建议大模型"
    )
    model_hint: str | None = None
    current_version_id: int | None = None
    current_version_no: int | None = None
    versions: list[PromptTemplateSummary] = Field(default_factory=list)


class CreateVersionRequest(BaseModel):
    scene: SceneLiteral
    name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=10)
    notes: str | None = None
    set_current: bool = True


class UpdateVersionRequest(BaseModel):
    """Only ``notes`` is mutable for an existing version. Editing content
    creates a NEW version (use create); this prevents silent drift in
    Questions/Attempts that froze a prompt_template_id (PRD §6.2.3).
    """

    notes: str | None = None


class SetCurrentResponse(BaseModel):
    scene: SceneLiteral
    current_version_id: int


class UpdateBindingRequest(BaseModel):
    model_id: int | None = None
    fallback_model_id: int | None = None
    params: dict | None = None
    fallback_params: dict | None = None


class PreviewRenderRequest(BaseModel):
    """Render a template with sample variables to spot-check formatting."""

    content: str
    variables: dict[str, str] = Field(default_factory=dict)


class PreviewRenderResponse(BaseModel):
    rendered: str
    missing_placeholders: list[str] = Field(default_factory=list)
    unused_variables: list[str] = Field(default_factory=list)
