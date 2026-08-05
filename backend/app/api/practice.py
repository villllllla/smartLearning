"""Practice endpoints — setup (resolve question pool) + answer (score+persist)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import Question
from app.schemas.practice import (
    PracticeAnswerRequest,
    PracticeAnswerResponse,
    PracticeSetupRequest,
    PracticeSetupResponse,
)
from app.services.llm import LLMError
from app.services.practice_service import setup_questions
from app.services.scoring_service import score_answer

router = APIRouter()


@router.post("/setup", response_model=PracticeSetupResponse)
def setup(
    payload: PracticeSetupRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> PracticeSetupResponse:
    return setup_questions(db, payload, tenant_id=ctx.tenant_id)


@router.post("/answer", response_model=PracticeAnswerResponse)
async def answer(
    payload: PracticeAnswerRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> PracticeAnswerResponse:
    q = db.get(Question, payload.question_id)
    if q is None or q.deleted_at is not None or q.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="question not found")
    if not payload.user_answer_text.strip():
        raise HTTPException(400, detail="作答不能为空")
    try:
        attempt = await score_answer(
            db,
            question=q,
            user_answer=payload.user_answer_text,
            override_model_id=payload.override_model_id,
            channel="web",
        )
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return PracticeAnswerResponse(
        attempt_id=attempt.id,
        question_id=attempt.question_id,
        grade=attempt.grade,  # type: ignore[arg-type]
        score_correctness=attempt.score_correctness,
        score_completeness=attempt.score_completeness,
        score_structure=attempt.score_structure,
        score_depth=attempt.score_depth,
        feedback_text=attempt.feedback_text,
    )
