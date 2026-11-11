"""revision source learned

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11

A revision made by re-fretting the tab with the learned weights (ADR-0016) is `learned`, so the
learning, which reads only `user` revisions, does not learn from its own output.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "source IN ('ai', 'user')"
NEW = "source IN ('ai', 'user', 'learned')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_tab_revisions_source"), "tab_revisions", type_="check")
    op.create_check_constraint(op.f("ck_tab_revisions_source"), "tab_revisions", NEW)


def downgrade() -> None:
    op.execute("UPDATE tab_revisions SET source = 'user' WHERE source = 'learned'")
    op.drop_constraint(op.f("ck_tab_revisions_source"), "tab_revisions", type_="check")
    op.create_check_constraint(op.f("ck_tab_revisions_source"), "tab_revisions", OLD)
