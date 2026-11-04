"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-04 14:28:56.997191
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending_upload", nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('mix', 'guitar_stem')", name=op.f("ck_audio_assets_source_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'uploaded', 'rejected')",
            name=op.f("ck_audio_assets_status"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_audio_assets_size_positive")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audio_assets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_assets")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_audio_assets_storage_key")),
    )
    op.create_index(op.f("ix_audio_assets_user_id"), "audio_assets", ["user_id"], unique=False)
    op.create_table(
        "tabs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("tuning", sa.Text(), server_default="E standard", nullable=False),
        sa.Column("visibility", sa.Text(), server_default="private", nullable=False),
        sa.Column("current_revision_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')", name=op.f("ck_tabs_visibility")
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200", name=op.f("ck_tabs_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_tabs_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tabs")),
    )
    op.create_index(op.f("ix_tabs_owner_id"), "tabs", ["owner_id"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("audio_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tab_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('separating', 'transcribing', 'arranging')",
            name=op.f("ck_jobs_stage"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_jobs_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.ForeignKeyConstraint(
            ["audio_id"],
            ["audio_assets.id"],
            name=op.f("fk_jobs_audio_id_audio_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tab_id"], ["tabs.id"], name=op.f("fk_jobs_tab_id_tabs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_audio_id"), "jobs", ["audio_id"], unique=False)
    op.create_index(
        "ix_jobs_queued",
        "jobs",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_table(
        "tab_revisions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tab_id", sa.UUID(), nullable=False),
        sa.Column("score", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('ai', 'user')", name=op.f("ck_tab_revisions_source")),
        sa.ForeignKeyConstraint(
            ["tab_id"], ["tabs.id"], name=op.f("fk_tab_revisions_tab_id_tabs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tab_revisions")),
    )
    op.create_index(op.f("ix_tab_revisions_tab_id"), "tab_revisions", ["tab_id"], unique=False)
    # tabs <-> tab_revisions is circular: add this FK once both tables exist.
    op.create_foreign_key(
        op.f("fk_tabs_current_revision_id_tab_revisions"),
        "tabs",
        "tab_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_tabs_current_revision_id_tab_revisions"), "tabs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_tab_revisions_tab_id"), table_name="tab_revisions")
    op.drop_table("tab_revisions")
    op.drop_index(
        "ix_jobs_queued", table_name="jobs", postgresql_where=sa.text("status = 'queued'")
    )
    op.drop_index(op.f("ix_jobs_audio_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_tabs_owner_id"), table_name="tabs")
    op.drop_table("tabs")
    op.drop_index(op.f("ix_audio_assets_user_id"), table_name="audio_assets")
    op.drop_table("audio_assets")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
