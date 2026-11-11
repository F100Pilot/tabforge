"""Learning the string/fret choice from the user's correct tabs (ADR-0011).

The worker tunes the weights; the API only marks the profile stale when the training data
changes (a reference saved or deleted, corrections applied, an edited revision saved) or when the
user asks ("Atualizar agora"), and shows the result.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tabforge_api.deps import CurrentUser, SessionDep, limit_writes
from tabforge_api.models import FrettingProfile

log = logging.getLogger("tabforge_api.tuning")
router = APIRouter(prefix="/v1/me", tags=["tuning"])

# Below these the worker does not tune (same values as tabforge_worker.learning).
MIN_NOTES = 200
MIN_TABS = 1  # ADR-0016
WEIGHT_NAMES = ("span", "height", "move", "open_move")


def mark_stale(session: Session, user_id: uuid.UUID) -> None:
    """Ask the worker to refresh the user's profile, in the caller's transaction.

    Runs in a savepoint and never raises: the request that changed the data must not fail
    because of the learning bookkeeping.
    """
    statement = (
        insert(FrettingProfile)
        .values(user_id=user_id, status="stale", requested_at=func.now())
        .on_conflict_do_update(
            index_elements=[FrettingProfile.user_id],
            set_={"status": "stale", "requested_at": func.now()},
        )
    )
    try:
        with session.begin_nested():
            session.execute(statement)
    except SQLAlchemyError:
        log.warning('{"event": "tuning_mark_failed", "user": "%s"}', user_id)


class WeightsOut(BaseModel):
    span: float
    height: float
    move: float
    open_move: float


class TuningOut(BaseModel):
    status: Literal["none", "stale", "ready", "insufficient"]
    tabs: int
    notes: int
    default_accuracy: float | None
    tuned_accuracy: float | None
    in_use: bool  # new jobs of this user use `weights`
    weights: WeightsOut | None
    updated_at: datetime | None
    min_notes: int = MIN_NOTES
    min_tabs: int = MIN_TABS


_STATUSES: dict[str, Literal["stale", "ready", "insufficient"]] = {
    "stale": "stale",
    "ready": "ready",
    "insufficient": "insufficient",
}


def _weights(value: Any) -> WeightsOut | None:
    if not isinstance(value, dict) or set(value) != set(WEIGHT_NAMES):
        return None
    return WeightsOut.model_validate(value)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _out(profile: FrettingProfile | None) -> TuningOut:
    if profile is None:
        return TuningOut(
            status="none",
            tabs=0,
            notes=0,
            default_accuracy=None,
            tuned_accuracy=None,
            in_use=False,
            weights=None,
            updated_at=None,
        )
    weights = _weights(profile.weights)
    status = _STATUSES[profile.status]
    return TuningOut(
        status=status,
        tabs=profile.tabs,
        notes=profile.notes,
        default_accuracy=_round(profile.default_accuracy),
        tuned_accuracy=_round(profile.tuned_accuracy),
        in_use=status == "ready" and weights is not None,
        weights=weights,
        updated_at=profile.updated_at,
    )


@router.get("/tuning")
def get_tuning(user: CurrentUser, session: SessionDep) -> TuningOut:
    return _out(session.get(FrettingProfile, user.id))


@router.post("/tuning", status_code=202, dependencies=[Depends(limit_writes)])
def refresh_tuning(user: CurrentUser, session: SessionDep) -> TuningOut:
    """ "Atualizar agora": mark the profile stale; the worker refreshes it within a minute."""
    mark_stale(session, user.id)
    profile = session.get(FrettingProfile, user.id, populate_existing=True)
    return _out(profile)
