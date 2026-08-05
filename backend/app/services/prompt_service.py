"""Prompt template + function binding business logic.

Versioning rules (PRD §6.2.3):
- Prompt content is never edited in-place. Editing creates a *new version*.
- ``is_current`` is unique per scene — flipping one to True flips the others
  to False inside a single transaction.
- Setting current also writes ``function_bindings.prompt_template_id`` so the
  scene-resolver in ``app/services/llm/client.py`` immediately picks it up.
- Versions referenced by frozen IDs (in Question / AnswerAttempt) are never
  truly deleted via API; we just refuse to delete them. Soft-delete is
  intentionally NOT applied — historical reproducibility relies on the row
  staying intact.
"""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AnswerAttempt,
    FunctionBinding,
    Model,
    ModelProvider,
    PromptTemplate,
    Question,
)

SCENE_INFO: dict[str, dict] = {
    "chat_general": {
        "title": "通用对话",
        "description": "对话页默认 system prompt;影响 Chat 中模型的口吻与回答结构。",
        "placeholders": [],
    },
    "wiki_to_questions": {
        "title": "Wiki → 面试题",
        "description": (
            "在 wiki 详情页点「生成面试题」时使用。控制题型/难度/答案结构。"
            "运行时占位符:{COUNT_DIRECTIVE} 由「自动/固定题量」开关注入,"
            "{N} / {MAX} 在固定模式或老版本模板中可用。"
        ),
        "placeholders": ["{COUNT_DIRECTIVE}", "{TITLE}", "{MARKDOWN}", "{N}", "{MAX}"],
        "model_tier": "capable",
        "model_hint": "建议选推理与结构化输出能力较强的模型。",
    },
    "answer_scoring": {
        "title": "作答评分",
        "description": "练习提交后用于打分;模型只输出 4 维分数 + 改进建议,grade 由服务端按硬规则算。",
        "placeholders": ["{QUESTION}", "{ANSWER_STANDARD}", "{USER_ANSWER}"],
        "model_tier": "capable",
        "model_hint": "建议选评分稳定、理解力强的模型。",
    },
    "wiki_summary": {
        "title": "Wiki 摘要(预留)",
        "description": "用于自动生成 wiki 摘要。当前 MVP 未在主流程使用,可备用。",
        "placeholders": ["{TITLE}", "{MARKDOWN}"],
    },
    "learning_note_structuring": {
        "title": "学习总结结构化",
        "description": (
            "把每日学习总结交给模型检验(指出错误/纠正)、结构化(标题/要点/分类)"
            "并打标签;用于飞书或网页提交学习总结时。运行时占位符:{RAW_INPUT}。"
        ),
        "placeholders": ["{RAW_INPUT}"],
    },
    "todo_intent_parsing": {
        "title": "待办意图解析",
        "description": (
            "飞书待办/提醒:解析创建、列表、完成意图,提取提醒时间;"
            "信息不足时生成澄清追问。占位符:{TIMEZONE} {NOW_LOCAL} {CONTEXT_JSON} {USER_MESSAGE}。"
        ),
        "placeholders": ["{TIMEZONE}", "{NOW_LOCAL}", "{CONTEXT_JSON}", "{USER_MESSAGE}"],
        "model_tier": "fast",
        "model_hint": "建议选小参数量、低延迟模型,追求快速响应。",
    },
    "ai_news_curation": {
        "title": "AI 资讯精选",
        "description": (
            "把多源抓取的 AI 资讯候选交给模型去重、按热度排序、生成中文标题与摘要;"
            "用于每日 AI 热点推送。占位符:{TOP_N} {CANDIDATES_JSON}。"
        ),
        "placeholders": ["{TOP_N}", "{CANDIDATES_JSON}"],
    },
    "plan_decomposition": {
        "title": "计划分解",
        "description": (
            "把一个大目标在日期区间内拆成按天分布的可执行小任务;用于导入学习/工作计划。"
            "占位符:{TITLE} {GOAL} {START_DATE} {END_DATE} {TODAY} {TIMEZONE}。"
        ),
        "placeholders": [
            "{TITLE}", "{GOAL}", "{START_DATE}", "{END_DATE}", "{TODAY}", "{TIMEZONE}"
        ],
    },
    "todo_motivation": {
        "title": "待办激励",
        "description": (
            "为长期延期的待办生成一句激励话语。占位符:{TASK_TITLE} {DEFER_DAYS}。"
        ),
        "placeholders": ["{TASK_TITLE}", "{DEFER_DAYS}"],
        "model_tier": "fast",
        "model_hint": "短文本生成,小模型即可。",
    },
    "interview_answer_generation": {
        "title": "面经参考答案",
        "description": (
            "导入实战面经后,按关联题组批量生成标准参考答案。"
            "占位符:{CONTEXT} {GROUP_LABEL} {QUESTIONS_JSON}。"
        ),
        "placeholders": ["{CONTEXT}", "{GROUP_LABEL}", "{QUESTIONS_JSON}"],
        "model_tier": "capable",
        "model_hint": "批量长答案生成,建议选上下文与质量更好的模型。",
    },
}

_PLACEHOLDER_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")


def repair_bindings_for_tenant(db: Session, *, tenant_id: int) -> None:
    """Point scene bindings at the current prompt when prompt_template_id is missing."""
    from app.prompts.defaults import DEFAULT_PROMPTS

    scenes = {p.scene for p in DEFAULT_PROMPTS}
    for scene in scenes:
        binding = get_binding(db, scene, tenant_id=tenant_id)
        if binding.prompt_template_id is not None:
            continue
        current = db.execute(
            select(PromptTemplate)
            .where(
                PromptTemplate.tenant_id == tenant_id,
                PromptTemplate.scene == scene,
                PromptTemplate.is_current.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if current is not None:
            binding.prompt_template_id = current.id
    db.flush()


def list_versions(db: Session, scene: str, *, tenant_id: int) -> list[PromptTemplate]:
    return list(
        db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.tenant_id == tenant_id, PromptTemplate.scene == scene)
            .order_by(PromptTemplate.version_no.desc())
        ).scalars().all()
    )


def get_binding(db: Session, scene: str, *, tenant_id: int) -> FunctionBinding:
    binding = db.execute(
        select(FunctionBinding).where(
            FunctionBinding.tenant_id == tenant_id,
            FunctionBinding.scene == scene,
        )
    ).scalar_one_or_none()
    if binding is None:
        binding = FunctionBinding(tenant_id=tenant_id, scene=scene, params_json={})
        db.add(binding)
        db.flush()
    return binding


def _next_version_no(db: Session, scene: str, *, tenant_id: int) -> int:
    last = db.execute(
        select(PromptTemplate.version_no)
        .where(PromptTemplate.tenant_id == tenant_id, PromptTemplate.scene == scene)
        .order_by(PromptTemplate.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (last or 0) + 1


def _flip_current(db: Session, scene: str, new_id: int, *, tenant_id: int) -> None:
    db.execute(
        update(PromptTemplate)
        .where(
            PromptTemplate.tenant_id == tenant_id,
            PromptTemplate.scene == scene,
            PromptTemplate.id != new_id,
        )
        .values(is_current=False)
    )
    db.execute(
        update(PromptTemplate)
        .where(PromptTemplate.id == new_id)
        .values(is_current=True)
    )
    binding = get_binding(db, scene, tenant_id=tenant_id)
    binding.prompt_template_id = new_id


def create_version(
    db: Session,
    *,
    tenant_id: int,
    scene: str,
    name: str,
    content: str,
    notes: str | None,
    set_current: bool,
) -> PromptTemplate:
    if scene not in SCENE_INFO:
        raise ValueError(f"unknown scene: {scene}")
    pt = PromptTemplate(
        tenant_id=tenant_id,
        scene=scene,
        name=name,
        content=content,
        version_no=_next_version_no(db, scene, tenant_id=tenant_id),
        notes=notes,
        is_current=False,
    )
    db.add(pt)
    db.flush()
    if set_current:
        _flip_current(db, scene, pt.id, tenant_id=tenant_id)
    db.flush()
    return pt


def set_current(db: Session, version_id: int, *, tenant_id: int) -> PromptTemplate:
    pt = db.get(PromptTemplate, version_id)
    if pt is None or pt.tenant_id != tenant_id:
        raise LookupError("version not found")
    _flip_current(db, pt.scene, pt.id, tenant_id=tenant_id)
    db.flush()
    return pt


def update_notes(db: Session, version_id: int, notes: str | None, *, tenant_id: int) -> PromptTemplate:
    pt = db.get(PromptTemplate, version_id)
    if pt is None or pt.tenant_id != tenant_id:
        raise LookupError("version not found")
    pt.notes = notes
    db.flush()
    return pt


def delete_version(db: Session, version_id: int, *, tenant_id: int) -> None:
    pt = db.get(PromptTemplate, version_id)
    if pt is None or pt.tenant_id != tenant_id:
        raise LookupError("version not found")
    if pt.is_current:
        raise ValueError("当前生效版本不可删除,请先把另一版本设为当前。")
    # 引用检查:被任何 Question / AnswerAttempt 冻结过的版本绝不能删
    refs_q = db.execute(
        select(Question.id).where(Question.generated_by_prompt_id == pt.id).limit(1)
    ).first()
    refs_a = db.execute(
        select(AnswerAttempt.id).where(AnswerAttempt.prompt_template_id == pt.id).limit(1)
    ).first()
    if refs_q or refs_a:
        raise ValueError(
            "该版本已被生成的题目或评分记录引用,不能删除(保留以便复现历史)。"
        )
    db.delete(pt)
    db.flush()


def update_binding(
    db: Session,
    scene: str,
    *,
    tenant_id: int,
    updates: dict,
) -> FunctionBinding:
    binding = get_binding(db, scene, tenant_id=tenant_id)
    if "model_id" in updates:
        binding.model_id = updates["model_id"]
    if "fallback_model_id" in updates:
        binding.fallback_model_id = updates["fallback_model_id"]
    if "params" in updates and updates["params"] is not None:
        binding.params_json = updates["params"]
    if "fallback_params" in updates and updates["fallback_params"] is not None:
        binding.fallback_params_json = updates["fallback_params"]
    db.flush()
    return binding


def render_preview(content: str, variables: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """Substitute ``{VAR}`` placeholders, returning (rendered, missing, unused)."""
    placeholders_in_template = set(_PLACEHOLDER_RE.findall(content))
    rendered = content
    used: set[str] = set()
    for key, value in variables.items():
        token = "{" + key + "}"
        if token in rendered:
            rendered = rendered.replace(token, str(value))
            used.add(key)
    missing = sorted(p for p in placeholders_in_template if p not in {k for k in variables})
    unused = sorted(k for k in variables if k not in used)
    return rendered, missing, unused


def all_scene_views(
    db: Session,
    *,
    tenant_id: int,
    schema_cls,
    summary_cls,
) -> list:
    """Compose ``SceneInfo`` rows: meta + binding + versions in one shot.

    `schema_cls` and `summary_cls` are passed in to avoid importing pydantic
    classes inside the service module (keeps service free of API concerns).
    """
    views = []
    for scene, meta in SCENE_INFO.items():
        binding = get_binding(db, scene, tenant_id=tenant_id)
        model: Model | None = (
            db.get(Model, binding.model_id) if binding.model_id is not None else None
        )
        fallback_model: Model | None = (
            db.get(Model, binding.fallback_model_id)
            if binding.fallback_model_id is not None
            else None
        )
        provider: ModelProvider | None = (
            db.get(ModelProvider, model.provider_id) if model else None
        )
        fallback_provider: ModelProvider | None = (
            db.get(ModelProvider, fallback_model.provider_id) if fallback_model else None
        )
        versions = list_versions(db, scene, tenant_id=tenant_id)
        current = next((v for v in versions if v.is_current), None)
        views.append(
            schema_cls(
                scene=scene,
                title=meta["title"],
                description=meta["description"],
                placeholders=meta["placeholders"],
                binding_model_id=binding.model_id,
                binding_model_name=model.name if model else None,
                binding_provider_name=provider.name if provider else None,
                binding_fallback_model_id=binding.fallback_model_id,
                binding_fallback_model_name=fallback_model.name if fallback_model else None,
                binding_fallback_provider_name=(
                    fallback_provider.name if fallback_provider else None
                ),
                binding_params=dict(binding.params_json or {}),
                binding_fallback_params=dict(binding.fallback_params_json or {}),
                model_tier=meta.get("model_tier"),
                model_hint=meta.get("model_hint"),
                current_version_id=current.id if current else None,
                current_version_no=current.version_no if current else None,
                versions=[summary_cls.model_validate(v) for v in versions],
            )
        )
    return views


def list_scenes(_db: Session) -> Iterable[str]:
    return SCENE_INFO.keys()
