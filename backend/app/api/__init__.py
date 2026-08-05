from fastapi import APIRouter

from app.integrations.feishu import router as feishu_router

from .ai_news import router as ai_news_router
from .auth import router as auth_router
from .bank import router as bank_router
from .branches import router as branches_router
from .chats import attachments_router
from .chats import router as chats_router
from .data import router as data_router
from .feishu_triggers import router as feishu_triggers_router
from .generation import router as generation_router
from .goals import router as goals_router
from .health import router as health_router
from .learning_notes import router as learning_notes_router
from .learning_review import router as learning_review_router
from .long_term_todos import router as long_term_todos_router
from .obsidian_sync import router as obsidian_sync_router
from .plans import router as plans_router
from .practice import router as practice_router
from .prompts import router as prompts_router
from .providers import router as providers_router
from .push_schedule import router as push_schedule_router
from .rag import router as rag_router
from .settings import router as settings_router
from .timezones import router as timezones_router
from .todos import router as todos_router
from .wikis import router as wikis_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(generation_router, tags=["generation"])
api_router.include_router(wikis_router, prefix="/wiki", tags=["wiki"])
api_router.include_router(branches_router, prefix="/wiki", tags=["wiki"])
api_router.include_router(providers_router, prefix="/providers", tags=["providers"])
api_router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
api_router.include_router(bank_router, prefix="/bank", tags=["bank"])
api_router.include_router(goals_router, prefix="/goals", tags=["goals"])
api_router.include_router(practice_router, prefix="/practice", tags=["practice"])
api_router.include_router(chats_router, prefix="/chats", tags=["chat"])
api_router.include_router(attachments_router, prefix="/attachments", tags=["chat"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(push_schedule_router, prefix="/push-schedule", tags=["push"])
api_router.include_router(
    learning_notes_router, prefix="/learning-notes", tags=["learning"]
)
api_router.include_router(
    learning_review_router, prefix="/learning-review", tags=["learning"]
)
api_router.include_router(todos_router, prefix="/todos", tags=["todos"])
api_router.include_router(plans_router, prefix="/plans", tags=["plans"])
api_router.include_router(
    long_term_todos_router, prefix="/long-term-todos", tags=["long-term-todos"]
)
api_router.include_router(ai_news_router, prefix="/ai-news", tags=["ai-news"])
api_router.include_router(timezones_router, prefix="/timezones", tags=["timezones"])
api_router.include_router(data_router, prefix="/data", tags=["data"])
api_router.include_router(
    obsidian_sync_router, prefix="/sync/obsidian", tags=["sync"]
)
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])
api_router.include_router(
    feishu_router, prefix="/integrations/feishu", tags=["integrations"]
)
api_router.include_router(
    feishu_triggers_router, prefix="/feishu-triggers", tags=["integrations"]
)
