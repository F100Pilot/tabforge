"""tab references

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04

ADR-0009: the correct tab of the same song, kept as note events (JSONB) to compare with the
transcription. One per tab; deleted with the tab (and so with the user, RGPD art. 17).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tab_references",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tab_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("track", sa.Text(), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tab_id"],
            ["tabs.id"],
            name=op.f("fk_tab_references_tab_id_tabs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tab_references")),
        sa.UniqueConstraint("tab_id", name=op.f("uq_tab_references_tab_id")),
    )


def downgrade() -> None:
    op.drop_table("tab_references")
