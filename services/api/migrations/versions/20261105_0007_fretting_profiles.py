"""fretting profiles

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05

ADR-0011: the string/fret weights learnt from each user's correct tabs and corrections, with the
accuracies that justify them. One per user; deleted with the account (RGPD art. 17).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fretting_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("default_accuracy", sa.Float(), nullable=True),
        sa.Column("tuned_accuracy", sa.Float(), nullable=True),
        sa.Column("tabs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.Text(), server_default="stale", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('stale', 'ready', 'insufficient')",
            name=op.f("ck_fretting_profiles_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_fretting_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_fretting_profiles")),
    )


def downgrade() -> None:
    op.drop_table("fretting_profiles")
