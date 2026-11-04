"""job stage normalizing

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04

The worker now decodes and checks audio (duration, format) in its own stage before
separation (docs/architecture.md, upload validation).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "stage IS NULL OR stage IN ('separating', 'transcribing', 'arranging')"
NEW = "stage IS NULL OR stage IN ('normalizing', 'separating', 'transcribing', 'arranging')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_jobs_stage"), "jobs", type_="check")
    op.create_check_constraint(op.f("ck_jobs_stage"), "jobs", NEW)


def downgrade() -> None:
    op.execute("UPDATE jobs SET stage = NULL WHERE stage = 'normalizing'")
    op.drop_constraint(op.f("ck_jobs_stage"), "jobs", type_="check")
    op.create_check_constraint(op.f("ck_jobs_stage"), "jobs", OLD)
