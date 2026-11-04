"""audio status expired

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04

Audio past its retention date (PRD §5, default 30 days) is deleted from storage and marked
`expired`; the tab made from it stays.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "status IN ('pending_upload', 'uploaded', 'rejected')"
NEW = "status IN ('pending_upload', 'uploaded', 'rejected', 'expired')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_audio_assets_status"), "audio_assets", type_="check")
    op.create_check_constraint(op.f("ck_audio_assets_status"), "audio_assets", NEW)


def downgrade() -> None:
    op.execute("UPDATE audio_assets SET status = 'rejected' WHERE status = 'expired'")
    op.drop_constraint(op.f("ck_audio_assets_status"), "audio_assets", type_="check")
    op.create_check_constraint(op.f("ck_audio_assets_status"), "audio_assets", OLD)
