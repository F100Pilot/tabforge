"""Job status (US-02). Ownership is checked through the job's audio asset (threat model T2)."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from tabforge_api.deps import CurrentUser, SessionDep
from tabforge_api.models import AudioAsset, Job
from tabforge_api.problems import ProblemError

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
