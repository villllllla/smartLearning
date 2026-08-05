"""wikis.obsidian_rel_path for vault dedup

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wikis",
        sa.Column("obsidian_rel_path", sa.String(500), nullable=True),
    )
    op.create_index("ix_wikis_obsidian_rel_path", "wikis", ["obsidian_rel_path"])


def downgrade() -> None:
    op.drop_index("ix_wikis_obsidian_rel_path", table_name="wikis")
    op.drop_column("wikis", "obsidian_rel_path")
