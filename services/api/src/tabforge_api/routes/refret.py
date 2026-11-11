"""Re-fret a tab with the user's learned weights (ADR-0016), as a new `learned` revision."""

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from tabforge_score.fretting import Weights
from tabforge_score.refret import refretted_score

from tabforge_api.deps import CurrentUser, SessionDep, limit_writes
from tabforge_api.models import FrettingProfile, TabRevision
from tabforge_api.problems import ProblemError
from tabforge_api.routes.references import _current_score
from tabforge_api.routes.tabs import TabOut, _tab_out, owned_tab
from tabforge_api.routes.tuning import _weights

router = APIRouter(prefix="/v1/tabs", tags=["tabs"])


class RefretIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: uuid.UUID


class RefretOut(BaseModel):
    tab: TabOut
    changed: int  # attacked notes on another string or fret


def learned_weights(session: Session, user_id: uuid.UUID) -> Weights | None:
    """The weights new jobs use (ADR-0011): a ready profile whose tuned weights were accepted."""
    profile = session.get(FrettingProfile, user_id)
    if profile is None or profile.status != "ready":
        return None
    weights = _weights(profile.weights)
    return None if weights is None else Weights(**weights.model_dump())


@router.post("/{tab_id}/refret", status_code=201, dependencies=[Depends(limit_writes)])
def refret_tab(
    tab_id: uuid.UUID, body: RefretIn, response: Response, user: CurrentUser, session: SessionDep
) -> RefretOut:
    """Choose the strings and frets of every track again; 200 and no revision if none move."""
    tab = owned_tab(session, user, tab_id, lock=True)
    weights = learned_weights(session, user.id)
    if weights is None:
        raise ProblemError(
            409, "no_learned_weights", "nothing learned yet: compare a tab with its correct tab"
        )
    current = _current_score(session, tab)
    if current is None:
        raise ProblemError(404, "not_found", "tab has no revision")
    if tab.current_revision_id != body.base_revision_id:
        raise ProblemError(
            409, "revision_conflict", "the tab changed since it was opened; reload before saving"
        )
    revision, score = current
    refretted, changed = refretted_score(score, weights)
    if changed == 0:
        response.status_code = 200
        return RefretOut(tab=_tab_out(tab, revision), changed=0)
    created = TabRevision(tab_id=tab.id, score=refretted.model_dump(mode="json"), source="learned")
    session.add(created)
    session.flush()
    tab.current_revision_id = created.id
    session.flush()
    session.refresh(created)
    # No mark_stale: the learning reads only `user` revisions, not its own output.
    return RefretOut(tab=_tab_out(tab, created), changed=changed)
