"""Job status (US-02). Ownership is checked through the job's audio asset (threat model T2)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select

from tabforge_api.deps import CurrentUser, SessionDep, StoreDep, limit_writes
from tabforge_api.models import AudioAsset, Job, Tab
from tabforge_api.problems import ProblemError
from tabforge_api.songs import delete_song, refuse_running

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None
    attempts: int
    error_code: str | None
    tab_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, job: Job) -> "JobOut":
        return cls(
            id=job.id,
            status=job.status,
            stage=job.stage,
            attempts=job.attempts,
            error_code=job.error_code,
            tab_id=job.tab_id,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class JobListItem(JobOut):
    source_kind: str
    duration_ms: int | None
    tab_title: str | None


class JobList(BaseModel):
    items: list[JobListItem]


@router.get("")
def list_jobs(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JobList:
    """The user's most recent jobs, newest first ("Recentes" on the upload page)."""
    rows = session.execute(
        select(Job, AudioAsset.source_kind, AudioAsset.duration_ms, Tab.title)
        .join(AudioAsset, AudioAsset.id == Job.audio_id)
        .outerjoin(Tab, Tab.id == Job.tab_id)
        .where(AudioAsset.user_id == user.id)
        .order_by(Job.created_at.desc())
        .limit(limit)
    ).all()
    return JobList(
        items=[
            JobListItem(
                **JobOut.from_model(job).model_dump(),
                source_kind=kind,
                duration_ms=duration,
                tab_title=title,
            )
            for job, kind, duration, title in rows
        ]
    )


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> JobOut:
    job = session.execute(
        select(Job)
        .join(AudioAsset, AudioAsset.id == Job.audio_id)
        .where(Job.id == job_id, AudioAsset.user_id == user.id)
    ).scalar_one_or_none()
    if job is None:
        raise ProblemError(404, "not_found", "job not found")
    return JobOut.from_model(job)


@router.delete("/{job_id}", status_code=204, dependencies=[Depends(limit_writes)])
def delete_job(
    job_id: uuid.UUID, user: CurrentUser, session: SessionDep, store: StoreDep
) -> Response:
    """Delete the song: the job's audio, the job and the tab it produced."""
    # FOR UPDATE: a job the worker is claiming is read again once it commits (now running).
    row = session.execute(
        select(Job, AudioAsset)
        .join(AudioAsset, AudioAsset.id == Job.audio_id)
        .where(Job.id == job_id, AudioAsset.user_id == user.id)
        .with_for_update(of=Job)
    ).first()
    if row is None:
        raise ProblemError(404, "not_found", "job not found")
    job, asset = row
    refuse_running([job])
    tab = session.get(Tab, job.tab_id) if job.tab_id is not None else None
    if tab is not None and tab.owner_id != user.id:
        tab = None
    delete_song(session, store, user.id, assets=[asset], tab=tab)
    return Response(status_code=204)
