"""timezone_refs reference table + seed major IANA zones

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timezone_refs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iana_name", sa.String(64), nullable=False),
        sa.Column("label_zh", sa.String(120), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("utc_offset_label", sa.String(16), nullable=False),
        sa.Column("utc_offset_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_timezone_refs_region", "timezone_refs", ["region"])
    op.create_index("ix_timezone_refs_iana_name", "timezone_refs", ["iana_name"], unique=True)

    from app.data.timezone_catalog import catalog_rows_for_seed

    table = sa.table(
        "timezone_refs",
        sa.column("iana_name", sa.String),
        sa.column("label_zh", sa.String),
        sa.column("region", sa.String),
        sa.column("utc_offset_label", sa.String),
        sa.column("utc_offset_minutes", sa.Integer),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(table, catalog_rows_for_seed())


def downgrade() -> None:
    op.drop_index("ix_timezone_refs_iana_name", table_name="timezone_refs")
    op.drop_index("ix_timezone_refs_region", table_name="timezone_refs")
    op.drop_table("timezone_refs")
