"""Reference tab (the correct tab of the same song) and its comparison with the AI tab (ADR-0009).

The browser reads the Guitar Pro file with alphaTab and sends only the notes. A tab keeps one
reference per track of its score (`?track=N`, 0 by default; ADR-0010).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from tabforge_score import Score
from tabforge_score.compare import NoteEvent, compare, score_events

from tabforge_api.deps import CurrentUser, SessionDep, limit_writes
from tabforge_api.models import Tab, TabReference, TabRevision
from tabforge_api.problems import ProblemError
from tabforge_api.routes.tabs import enforce_body_limit, owned_tab

router = APIRouter(prefix="/v1/tabs", tags=["reference"])

MAX_REFERENCE_BYTES = 2_000_000
MAX_REFERENCE_NOTES = 20_000

# Index of the tab's track (Score.track_list()); v1/v2 scores only have track 0. The upper
# bound is the Postgres integer column's, so GET/DELETE of any valid index just find nothing.
TrackQuery = Annotated[int, Query(ge=0, le=2**31 - 1)]


async def _limit_body(request: Request) -> None:
    await enforce_body_limit(request, MAX_REFERENCE_BYTES)


class ReferenceNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onset: Annotated[float, Field(ge=0, le=100_000)]  # quarter notes from the start
    pitch: Annotated[int, Field(ge=0, le=127)]
    string: Annotated[int, Field(ge=1, le=6)]  # 1 = highest string
    fret: Annotated[int, Field(ge=0, le=30)]
    bar: Annotated[int, Field(ge=1, le=10_000)]


class ReferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, Field(min_length=1, max_length=200)]
    track: Annotated[str, Field(max_length=200)]
    notes: Annotated[list[ReferenceNote], Field(min_length=1, max_length=MAX_REFERENCE_NOTES)]


class ReferenceOut(BaseModel):
    filename: str
    track: str
    notes: int
    created_at: datetime


class BarOut(BaseModel):
    bar: int
    reference_notes: int
    matched: int
    positions_ok: int


class ComparisonOut(BaseModel):
    revision_id: uuid.UUID
    shift_quarters: float
    scale: float
    matched: int
    ai_notes: int
    reference_notes: int
    recall: float
    precision: float
    f1: float
    position_accuracy: float | None
    onset_error: float | None
    bars: list[BarOut]


def _out(reference: TabReference) -> ReferenceOut:
    return ReferenceOut(
        filename=reference.filename,
        track=reference.track,
        notes=len(reference.notes),
        created_at=reference.created_at,
    )


def _find(session: SessionDep, tab: Tab, track: int) -> TabReference | None:
    return session.execute(
        select(TabReference).where(TabReference.tab_id == tab.id, TabReference.track_index == track)
    ).scalar_one_or_none()


def _not_found() -> ProblemError:
    return ProblemError(404, "reference_not_found", "this track of the tab has no reference tab")


def _current_score(session: SessionDep, tab: Tab) -> tuple[TabRevision, Score] | None:
    revision = session.execute(
        select(TabRevision).where(TabRevision.id == tab.current_revision_id)
    ).scalar_one_or_none()
    if revision is None:
        return None
    return revision, Score.model_validate(revision.score)


def _check_track(score: Score | None, track: int) -> None:
    """The track must exist in the current revision (a tab without one only has track 0)."""
    count = 1 if score is None else len(score.track_list())
    if track >= count:
        raise ProblemError(
            422, "invalid_track", f"track {track} does not exist, the tab has {count}"
        )


@router.put("/{tab_id}/reference", dependencies=[Depends(_limit_body), Depends(limit_writes)])
def put_reference(
    tab_id: uuid.UUID,
    body: ReferenceIn,
    user: CurrentUser,
    session: SessionDep,
    track: TrackQuery = 0,
) -> ReferenceOut:
    """Store the reference notes of one track, replacing its previous one."""
    tab = owned_tab(session, user, tab_id, lock=True)  # the lock serializes concurrent PUTs
    current = _current_score(session, tab)
    _check_track(None if current is None else current[1], track)
    session.execute(
        delete(TabReference).where(TabReference.tab_id == tab.id, TabReference.track_index == track)
    )
    reference = TabReference(
        tab_id=tab.id,
        track_index=track,
        filename=body.filename,
        track=body.track,
        notes=[n.model_dump() for n in body.notes],
    )
    session.add(reference)
    session.flush()
    session.refresh(reference)
    return _out(reference)


@router.get("/{tab_id}/reference")
def get_reference(
    tab_id: uuid.UUID, user: CurrentUser, session: SessionDep, track: TrackQuery = 0
) -> ReferenceOut:
    tab = owned_tab(session, user, tab_id)
    reference = _find(session, tab, track)
    if reference is None:
        raise _not_found()
    return _out(reference)


@router.delete("/{tab_id}/reference", status_code=204, dependencies=[Depends(limit_writes)])
def delete_reference(
    tab_id: uuid.UUID, user: CurrentUser, session: SessionDep, track: TrackQuery = 0
) -> Response:
    tab = owned_tab(session, user, tab_id)
    session.execute(
        delete(TabReference).where(TabReference.tab_id == tab.id, TabReference.track_index == track)
    )
    return Response(status_code=204)


@router.get("/{tab_id}/comparison")
def get_comparison(
    tab_id: uuid.UUID, user: CurrentUser, session: SessionDep, track: TrackQuery = 0
) -> ComparisonOut:
    """One track of the tab's current revision against that track's reference notes."""
    tab = owned_tab(session, user, tab_id)
    current = _current_score(session, tab)
    if current is None:
        raise ProblemError(404, "not_found", "tab has no revision")
    revision, score = current
    _check_track(score, track)
    reference = _find(session, tab, track)
    if reference is None:
        raise _not_found()
    ai = score_events(score, track)
    ref = [NoteEvent(**n) for n in reference.notes]
    result = compare(ai, ref)

    def r(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    return ComparisonOut(
        revision_id=revision.id,
        shift_quarters=round(result.shift, 4),
        scale=round(result.scale, 4),
        matched=result.matched,
        ai_notes=result.ai_notes,
        reference_notes=result.reference_notes,
        recall=round(result.recall, 4),
        precision=round(result.precision, 4),
        f1=round(result.f1, 4),
        position_accuracy=r(result.position_accuracy),
        onset_error=r(result.onset_error),
        bars=[
            BarOut(
                bar=b.bar,
                reference_notes=b.reference_notes,
                matched=b.matched,
                positions_ok=b.positions_ok,
            )
            for b in result.bars
        ],
    )
