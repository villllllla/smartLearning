"""Initial schema + default prompt seeds.

Revision ID: 0001
Revises:
Create Date: 2026-05-12

This migration creates the full PRD §6 schema in a single step. We avoid
piecemeal autogenerate so the first install is deterministic.
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Wiki ---------------------------------------------------------------
    op.create_table(
        "wiki_collections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("wiki_collections.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Integer),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "wikis",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("wiki_collections.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Integer),
        sa.Column("current_main_commit_id", sa.Integer, nullable=True),  # FK added later
        sa.Column("word_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("excerpt", sa.Text),
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_wikis_title", "wikis", ["title"])
    op.create_index("ix_wikis_deleted", "wikis", ["deleted_at"])

    op.create_table(
        "wiki_branches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("wiki_id", sa.Integer, sa.ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("head_commit_id", sa.Integer, nullable=True),  # FK added later
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index(
        "ix_wiki_branches_wiki_name", "wiki_branches", ["wiki_id", "name"], unique=True
    )

    op.create_table(
        "wiki_commits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("wiki_id", sa.Integer, sa.ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("wiki_branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_commit_id", sa.Integer, sa.ForeignKey("wiki_commits.id", ondelete="SET NULL")),
        sa.Column("author_id", sa.Integer),
        sa.Column("message", sa.String(500), nullable=False, server_default=""),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_wiki_commits_wiki", "wiki_commits", ["wiki_id"])
    op.create_index("ix_wiki_commits_branch", "wiki_commits", ["branch_id"])

    # Add deferred FKs (wikis.current_main_commit_id, wiki_branches.head_commit_id)
    with op.batch_alter_table("wikis") as batch:
        batch.create_foreign_key(
            "fk_wikis_current_commit",
            "wiki_commits",
            ["current_main_commit_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("wiki_branches") as batch:
        batch.create_foreign_key(
            "fk_branch_head_commit",
            "wiki_commits",
            ["head_commit_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ---- Provider / Model ---------------------------------------------------
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("api_key_encrypted", sa.String(2000)),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "models",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.Integer, sa.ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("supports_vision", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("supports_streaming", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("context_window", sa.Integer, nullable=False, server_default="8192"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("provider_id", "name", name="uq_model_provider_name"),
    )

    # ---- Prompt -------------------------------------------------------------
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scene", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("scene", "version_no", name="uq_prompt_scene_version"),
    )
    op.create_index("ix_prompts_scene_version", "prompt_templates", ["scene", "version_no"])

    op.create_table(
        "function_bindings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scene", sa.String(32), nullable=False, unique=True),
        sa.Column("prompt_template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="SET NULL")),
        sa.Column("model_id", sa.Integer, sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("params_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    # ---- Question Bank ------------------------------------------------------
    op.create_table(
        "question_bank_collections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("question_bank_collections.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Integer),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("question_bank_collections.id", ondelete="SET NULL")),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("answer_standard", sa.Text, nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("qtype", sa.String(16), nullable=False, server_default="concept"),
        sa.Column("source_wiki_id", sa.Integer, sa.ForeignKey("wikis.id", ondelete="SET NULL")),
        sa.Column("source_commit_id", sa.Integer, sa.ForeignKey("wiki_commits.id", ondelete="SET NULL")),
        sa.Column("source_anchor", sa.String(64)),
        sa.Column("generated_by_prompt_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="SET NULL")),
        sa.Column("generated_by_model_id", sa.Integer, sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_questions_collection", "questions", ["collection_id"])
    op.create_index("ix_questions_source_wiki", "questions", ["source_wiki_id"])
    op.create_index("ix_questions_difficulty", "questions", ["difficulty"])

    op.create_table(
        "question_tags",
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "question_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("picked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("edited", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_wiki_id", sa.Integer, sa.ForeignKey("wikis.id", ondelete="SET NULL")),
        sa.Column("source_commit_id", sa.Integer, sa.ForeignKey("wiki_commits.id", ondelete="SET NULL")),
        sa.Column("generated_by_prompt_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="SET NULL")),
        sa.Column("generated_by_model_id", sa.Integer, sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("batch_id", "id", name="uq_candidate_batch_id"),
    )
    op.create_index("ix_question_candidates_batch", "question_candidates", ["batch_id"])

    # ---- Practice -----------------------------------------------------------
    op.create_table(
        "answer_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer),
        sa.Column("user_answer_text", sa.Text, nullable=False),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("score_correctness", sa.Integer, nullable=False),
        sa.Column("score_completeness", sa.Integer, nullable=False),
        sa.Column("score_structure", sa.Integer, nullable=False),
        sa.Column("score_depth", sa.Integer, nullable=False),
        sa.Column("feedback_text", sa.Text, nullable=False, server_default=""),
        sa.Column("model_id", sa.Integer, sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("prompt_template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_attempts_question_created", "answer_attempts", ["question_id", "created_at"])

    # ---- Chat ---------------------------------------------------------------
    op.create_table(
        "chats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False, server_default="新对话"),
        sa.Column("model_id", sa.Integer, sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("prompt_template_id", sa.Integer, sa.ForeignKey("prompt_templates.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_text", sa.Text, nullable=False, server_default=""),
        sa.Column("attachments_json", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("token_usage_json", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_messages_chat", "messages", ["chat_id"])

    # ---- Seed default prompts (PRD §6.3.6 / §6.4.5) -------------------------
    from app.prompts.defaults import DEFAULT_PROMPTS

    bind = op.get_bind()
    now = datetime.utcnow()
    for p in DEFAULT_PROMPTS:
        bind.execute(
            sa.text(
                """
                INSERT INTO prompt_templates
                  (name, scene, content, version_no, is_current, notes, created_at, updated_at)
                VALUES
                  (:name, :scene, :content, 1, 1, :notes, :now, :now)
                """
            ),
            {
                "name": p.name,
                "scene": p.scene,
                "content": p.content,
                "notes": "默认 v1,系统初始化时写入",
                "now": now,
            },
        )

    # Pre-create function bindings (model_id stays NULL until user configures one)
    for scene in ("wiki_to_questions", "answer_scoring", "chat_general", "wiki_summary"):
        prompt_id = bind.execute(
            sa.text(
                "SELECT id FROM prompt_templates WHERE scene = :scene AND is_current = 1"
            ),
            {"scene": scene},
        ).scalar()
        bind.execute(
            sa.text(
                """
                INSERT INTO function_bindings
                  (scene, prompt_template_id, model_id, params_json, created_at, updated_at)
                VALUES (:scene, :prompt_id, NULL, '{}', :now, :now)
                """
            ),
            {"scene": scene, "prompt_id": prompt_id, "now": now},
        )


def downgrade() -> None:
    for table in (
        "messages",
        "chats",
        "answer_attempts",
        "question_candidates",
        "question_tags",
        "questions",
        "tags",
        "question_bank_collections",
        "function_bindings",
        "prompt_templates",
        "models",
        "model_providers",
        "wiki_commits",
        "wiki_branches",
        "wikis",
        "wiki_collections",
    ):
        op.drop_table(table)
