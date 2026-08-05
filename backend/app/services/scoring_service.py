"""Answer scoring (PRD §6.4).

Calls scene='answer_scoring' LLM, validates JSON via schema, computes
``grade`` server-side using ``ScoringDefaults.grade`` (single source of truth),
persists ``AnswerAttempt`` with frozen prompt/model ids, then trims old
attempts beyond ``app_settings.practice_history_keep_n`` for that question.
"""
from __future__ import annotations

import logging

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AnswerAttempt, Question
from app.prompts.defaults import ScoringDefaults
from app.services.llm import LLMClient, LLMMessage
from app.services.settings_service import get_settings_row

log = logging.getLogger(__name__)


SCORING_SCHEMA: dict = {
    "type": "object",
    "required": [
        "score_correctness",
        "score_completeness",
        "score_structure",
        "score_depth",
        "feedback",
        "summary",
    ],
    "properties": {
        "score_correctness": {"type": "integer", "minimum": 0, "maximum": 100},
        "score_completeness": {"type": "integer", "minimum": 0, "maximum": 100},
        "score_structure": {"type": "integer", "minimum": 0, "maximum": 100},
        "score_depth": {"type": "integer", "minimum": 0, "maximum": 100},
        "feedback": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 8,
        },
        "summary": {"type": "string"},
    },
    "additionalProperties": False,
}


def _render_prompt(
    template: str, *, question: str, answer_standard: str, user_answer: str
) -> str:
    out = template
    for placeholder, value in (
        ("{QUESTION}", question),
        ("{ANSWER_STANDARD}", answer_standard),
        ("{USER_ANSWER}", user_answer),
    ):
        out = out.replace(placeholder, value)
    return out


async def score_answer(
    db: Session,
    *,
    question: Question,
    user_answer: str,
    override_model_id: int | None = None,
    channel: str | None = None,
    feishu_open_id: str | None = None,
    feishu_message_id: str | None = None,
    bot_session_id: int | None = None,
) -> AnswerAttempt:
    """Run scoring, persist AnswerAttempt, return it (uncommitted by this fn)."""
    client, prompt = LLMClient.for_scene(
        db,
        "answer_scoring",
        tenant_id=question.tenant_id,
        override_model_id=override_model_id,
    )
    rendered = _render_prompt(
        prompt.content,
        question=question.question_text,
        answer_standard=question.answer_standard or "(无)",
        user_answer=user_answer,
    )
    messages = [LLMMessage(role="user", content=rendered)]
    data, _ = await client.chat_json(messages, schema=SCORING_SCHEMA)

    correctness = int(data["score_correctness"])
    completeness = int(data["score_completeness"])
    structure = int(data["score_structure"])
    depth = int(data["score_depth"])
    grade = ScoringDefaults.grade(correctness, completeness, structure, depth)

    feedback_lines = [str(line) for line in data.get("feedback", [])]
    summary_line = str(data.get("summary", "")).strip()
    body = "\n".join(["- " + ln for ln in feedback_lines])
    feedback_text = f"{summary_line}\n\n{body}".strip() if summary_line else body

    attempt = AnswerAttempt(
        question_id=question.id,
        user_answer_text=user_answer,
        grade=grade,
        score_correctness=correctness,
        score_completeness=completeness,
        score_structure=structure,
        score_depth=depth,
        feedback_text=feedback_text,
        model_id=client.model.id,
        prompt_template_id=prompt.id,
        channel=channel,
        feishu_open_id=feishu_open_id,
        feishu_message_id=feishu_message_id,
        bot_session_id=bot_session_id,
    )
    db.add(attempt)
    db.flush()

    # PRD §6.4.3: keep only most recent N attempts per question (rolling window)
    keep_n = get_settings_row(db, question.tenant_id).practice_history_keep_n
    if keep_n > 0:
        keep_ids = (
            db.execute(
                select(AnswerAttempt.id)
                .where(AnswerAttempt.question_id == question.id)
                .order_by(desc(AnswerAttempt.created_at))
                .limit(keep_n)
            )
            .scalars()
            .all()
        )
        if keep_ids:
            stale = (
                db.execute(
                    select(AnswerAttempt)
                    .where(
                        AnswerAttempt.question_id == question.id,
                        AnswerAttempt.id.notin_(keep_ids),
                    )
                )
                .scalars()
                .all()
            )
            for s in stale:
                db.delete(s)
            db.flush()
    return attempt
