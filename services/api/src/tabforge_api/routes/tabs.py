"""Tabs (US-03) and their immutable revisions (US-04)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from tabforge_score import Score, to_alphatex

from tabforge_api.deps import CurrentUser, SessionDep, limit_writes
from tabforge_api.models import Tab, TabRevision
from tabforge_api.problems import ProblemError

router = APIRouter(prefix="/v1/tabs", tags=["tabs"])

MAX_REVISION_BYTES = 1_000_000  # a 2000-bar score is well under this


async def _limit_body(request: Request) -> None:
    """Refuse oversized bodies before they are parsed (memory exhaustion)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_REVISION_BYTES:
        raise ProblemError(413, "payload_too_large", f"maximum body is {MAX_REVISION_BYTES} bytes")
    if len(await request.body()) > MAX_REVISION_BYTES:
        raise ProblemError(413, "payload_too_large", f"maximum body is {MAX_REVISION_BYTES} bytes")


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


def _owned_tab(
    session: SessionDep, user: CurrentUser, tab_id: uuid.UUID, lock: bool = False
) -> Tab:
    query = select(Tab).where(Tab.id == tab_id, Tab.owner_id == user.id)
    tab = session.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if tab is None:
        raise ProblemError(404, "not_found", "tab not found")
    return tab


def _revision_out(revision: TabRevision) -> RevisionOut:
    # Stored scores are validated again on read: alphaTex only ever comes from a valid Score.
    score = Score.model_validate(revision.score)
    return RevisionOut(
        id=revision.id,
        source=revision.source,
        created_at=revision.created_at,
        score=score.model_dump(mode="json"),
    )


def _tab_out(tab: Tab, revision: TabRevision) -> TabOut:
    out = _revision_out(revision)
    return TabOut(
        id=tab.id,
        title=tab.title,
        tuning=tab.tuning,
        visibility=tab.visibility,
        created_at=tab.created_at,
        revision=out,
        alphatex=to_alphatex(Score.model_validate(out.score), tab.title),
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
    return _tab_out(tab, revision)


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The revision the editor started from; a different current revision means someone
    # saved in the meantime (another tab or device) and this save would overwrite it.
    base_revision_id: uuid.UUID
    score: Score


class RevisionSummary(BaseModel):
    id: uuid.UUID
    source: str
    created_at: datetime


class RevisionList(BaseModel):
    items: list[RevisionSummary]


@router.post(
    "/{tab_id}/revisions",
    status_code=201,
    dependencies=[Depends(_limit_body), Depends(limit_writes)],
)
def create_revision(
    tab_id: uuid.UUID, body: RevisionCreate, user: CurrentUser, session: SessionDep
) -> TabOut:
    """Save an edit as a new immutable revision and make it current (US-04)."""
    tab = _owned_tab(session, user, tab_id, lock=True)
    if tab.current_revision_id != body.base_revision_id:
        raise ProblemError(
            409, "revision_conflict", "the tab changed since it was opened; reload before saving"
        )
    revision = TabRevision(tab_id=tab.id, score=body.score.model_dump(mode="json"), source="user")
    session.add(revision)
    session.flush()
    tab.current_revision_id = revision.id
    session.flush()
    session.refresh(revision)
    return _tab_out(tab, revision)


@router.get("/{tab_id}/revisions")
def list_revisions(tab_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RevisionList:
    tab = _owned_tab(session, user, tab_id)
    rows = session.execute(
        select(TabRevision.id, TabRevision.source, TabRevision.created_at)
        .where(TabRevision.tab_id == tab.id)
        .order_by(TabRevision.created_at.desc(), TabRevision.id.desc())
    ).all()
    return RevisionList(items=[RevisionSummary(id=i, source=s, created_at=c) for i, s, c in rows])


@router.get("/{tab_id}/revisions/{revision_id}")
def get_revision(
    tab_id: uuid.UUID, revision_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RevisionOut:
    tab = _owned_tab(session, user, tab_id)
    revision = session.execute(
        select(TabRevision).where(TabRevision.id == revision_id, TabRevision.tab_id == tab.id)
    ).scalar_one_or_none()
    if revision is None:
        raise ProblemError(404, "not_found", "revision not found")
    return _revision_out(revision)
