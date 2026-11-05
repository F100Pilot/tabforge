"""tab reference per track

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05

ADR-0010: a Score v3 tab has up to four tracks (Lead, Rhythm...), each compared with its own
correct tab. `track_index` is the index of the tab's track (0 for v1/v2 scores and for the
references stored before this migration); one reference per tab and track.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tab_references",
        sa.Column("track_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_tab_references_track_index_non_negative"), "tab_references", "track_index >= 0"
    )
    op.drop_constraint(op.f("uq_tab_references_tab_id"), "tab_references", type_="unique")
    op.create_unique_constraint(
        op.f("uq_tab_references_tab_id_track_index"), "tab_references", ["tab_id", "track_index"]
    )


def downgrade() -> None:
    # Back to one reference per tab: the references of the other tracks are lost.
    op.execute("DELETE FROM tab_references WHERE track_index <> 0")
    op.drop_constraint(
        op.f("uq_tab_references_tab_id_track_index"), "tab_references", type_="unique"
    )
    op.create_unique_constraint(op.f("uq_tab_references_tab_id"), "tab_references", ["tab_id"])
    op.drop_constraint(
        op.f("ck_tab_references_track_index_non_negative"), "tab_references", type_="check"
    )
    op.drop_column("tab_references", "track_index")
