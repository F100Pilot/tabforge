"""Deleting one song: its audio objects, then its rows (the same order as US-07)."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tabforge_api.models import AudioAsset, Job, Tab, TabReference
from tabforge_api.problems import ProblemError
from tabforge_api.routes.tuning import mark_stale
from tabforge_api.storage import ObjectStore

log = logging.getLogger("tabforge_api.songs")


def refuse_running(jobs: list[Job]) -> None:
    """The worker is writing a running job's tab; deleting under it would lose its work."""
    if any(job.status == "running" for job in jobs):
        raise ProblemError(409, "job_running", "the transcription is running; try again later")


def delete_song(
    session: Session,
    store: ObjectStore,
    user_id: uuid.UUID,
    *,
    assets: list[AudioAsset],
    tab: Tab | None,
) -> None:
    """Storage first: if it fails nothing is deleted and the user can retry (idempotent).

    Deleting the assets cascades to their jobs; deleting the tab to its revisions and
    references. A copy saved to the Music folder (ADR-0014) is the user's file and stays.
    """
    try:
        for asset in assets:
            if asset.status != "expired":
                store.delete(asset.storage_key)
    except Exception as exc:
        log.warning('{"event": "song_delete_storage_failed", "user": "%s"}', user_id)
        raise ProblemError(
            503, "storage_unavailable", "could not delete stored audio; try again later"
        ) from exc
    had_reference = (
        tab is not None
        and session.execute(
            select(TabReference.id).where(TabReference.tab_id == tab.id).limit(1)
        ).first()
        is not None
    )
    if assets:
        session.execute(delete(AudioAsset).where(AudioAsset.id.in_([a.id for a in assets])))
    if tab is not None:
        session.execute(delete(Tab).where(Tab.id == tab.id))
    if had_reference:
        mark_stale(session, user_id)  # less training data (ADR-0011)
    session.commit()
    log.info('{"event": "song_deleted", "user": "%s"}', user_id)
