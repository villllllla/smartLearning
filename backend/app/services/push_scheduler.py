"""Background loop for scheduled question pushes."""
from __future__ import annotations

import asyncio
import logging

from app.db.session import SessionLocal
from app.services.ai_news_service import run_due_ai_news
from app.services.learning_review_service import run_due_learning_reviews
from app.services.push_schedule_service import run_due_pushes
from app.services.todo_check_service import run_due_todo_check
from app.services.todo_service import run_deferrals_all_tenants, run_due_todo_reminders

log = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_answer_task: asyncio.Task | None = None


async def _loop() -> None:
    await asyncio.sleep(5)
    while True:
        try:
            db = SessionLocal()
            try:
                await run_due_pushes(db)
            finally:
                db.close()
            db = SessionLocal()
            try:
                await run_due_learning_reviews(db)
            finally:
                db.close()
            db = SessionLocal()
            try:
                run_deferrals_all_tenants(db)
                db.commit()
            finally:
                db.close()
            db = SessionLocal()
            try:
                await run_due_todo_reminders(db)
                db.commit()
            finally:
                db.close()
            db = SessionLocal()
            try:
                await run_due_ai_news(db)
            finally:
                db.close()
            db = SessionLocal()
            try:
                await run_due_todo_check(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("push scheduler tick failed")
        await asyncio.sleep(60)


async def _interview_answer_loop() -> None:
    from app.services.interview_answer_service import process_next_batch

    await asyncio.sleep(8)
    while True:
        processed = False
        try:
            db = SessionLocal()
            try:
                processed = await process_next_batch(db)
                if processed:
                    db.commit()
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("interview answer queue tick failed")
        await asyncio.sleep(8 if processed else 25)


def start_push_scheduler() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    log.info("question push scheduler started (60s tick)")


def start_interview_answer_scheduler() -> None:
    global _answer_task
    if _answer_task is not None and not _answer_task.done():
        return
    _answer_task = asyncio.create_task(_interview_answer_loop())
    log.info("interview answer queue started (8s tick)")


def stop_push_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None


def stop_interview_answer_scheduler() -> None:
    global _answer_task
    if _answer_task is not None:
        _answer_task.cancel()
        _answer_task = None
