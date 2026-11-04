"""Read a tab with its current revision and the alphaTex rendered from it (US-03)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from tabforge_score import Score, to_alphatex

from tabforge_api.deps import CurrentUser, SessionDep
from tabforge_api.models import Tab, TabRevision
from tabforge_api.problems import ProblemError

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


class TabSummary(BaseModel):
    id: uuid.UUID
    title: str
    tuning: str
    visibility: str
    created_at: datetime


class TabList(BaseModel):
    items: list[TabSummary]


@router.get("")
def list_tabs(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TabList:
    tabs = session.execute(
        select(Tab).where(Tab.owner_id == user.id).order_by(Tab.created_at.desc()).limit(limit)
    ).scalars()
    return TabList(
        items=[
            TabSummary(
                id=t.id,
                title=t.title,
                tuning=t.tuning,
                visibility=t.visibility,
                created_at=t.created_at,
            )
            for t in tabs
        ]
    )


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
