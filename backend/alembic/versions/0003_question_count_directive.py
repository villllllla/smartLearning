"""Switch wiki_to_questions v1 default to use {COUNT_DIRECTIVE}.

We only rewrite a row when its content is *byte-identical* to the legacy
default text — that way custom edits by the user (or any later version they
authored) are left alone.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import here so alembic doesn't pull the whole app at module-load time.
    from app.prompts.defaults import (
        WIKI_TO_QUESTIONS_V1,
        WIKI_TO_QUESTIONS_V1_LEGACY,
    )

    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "UPDATE prompt_templates "
            "SET content = :new_content "
            "WHERE scene = 'wiki_to_questions' "
            "  AND content = :old_content"
        ),
        {
            "new_content": WIKI_TO_QUESTIONS_V1,
            "old_content": WIKI_TO_QUESTIONS_V1_LEGACY,
        },
    )
    # Surface the actual count so an operator running `alembic upgrade` knows
    # whether their installation got the new text or kept their custom one.
    try:
        rowcount = result.rowcount  # type: ignore[attr-defined]
    except AttributeError:
        rowcount = None
    print(
        f"[0003] wiki_to_questions default refresh: "
        f"{rowcount if rowcount is not None else 'unknown'} row(s) updated"
    )


def downgrade() -> None:
    from app.prompts.defaults import (
        WIKI_TO_QUESTIONS_V1,
        WIKI_TO_QUESTIONS_V1_LEGACY,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE prompt_templates "
            "SET content = :old_content "
            "WHERE scene = 'wiki_to_questions' "
            "  AND content = :new_content"
        ),
        {
            "new_content": WIKI_TO_QUESTIONS_V1,
            "old_content": WIKI_TO_QUESTIONS_V1_LEGACY,
        },
    )
