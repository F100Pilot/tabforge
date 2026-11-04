"""Read a tab with its current revision and the alphaTex rendered from it (US-03)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from tabforge_api.deps import CurrentUser, SessionDep
from tabforge_api.models import Tab, TabRevision
from tabforge_api.problems import ProblemError
from tabforge_api.score import Score, to_alphatex

router = APIRouter(prefix="/v1/tabs", tags=["tabs"])


class RevisionOut(BaseModel):
    id: uuid.UUID
    source: str
    created_at: datetime
    score: dict[str, Any]


class TabOut(BaseModel):
    id: uuid.UUID
    title: str
    tuning: str
    visibility: str
    created_at: datetime
    revision: RevisionOut
    alphatex: str


@router.get("/{tab_id}")
def get_tab(tab_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TabOut:
    row = session.execute(
        select(Tab, TabRevision)
        .join(TabRevision, TabRevision.id == Tab.current_revision_id)
        .where(Tab.id == tab_id, Tab.owner_id == user.id)
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not_found", "tab not found")
    tab, revision = row
    # Stored scores are validated again on read: alphaTex only ever comes from a valid Score.
    score = Score.model_validate(revision.score)
    return TabOut(
        id=tab.id,
        title=tab.title,
        tuning=tab.tuning,
        visibility=tab.visibility,
        created_at=tab.created_at,
        revision=RevisionOut(
            id=revision.id,
            source=revision.source,
            created_at=revision.created_at,
            score=score.model_dump(mode="json"),
        ),
        alphatex=to_alphatex(score, tab.title),
    )
