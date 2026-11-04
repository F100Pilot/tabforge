"""US-01: pre-signed upload, then completion with content validation and job creation."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from tabforge_api.audio_types import SNIFF_BYTES, normalize_declared_type, sniff_audio_type
from tabforge_api.deps import CurrentUser, SessionDep, SettingsDep, StoreDep, limit_writes
from tabforge_api.models import AudioAsset, Job
from tabforge_api.problems import ProblemError
from tabforge_api.routes.jobs import JobOut

router = APIRouter(prefix="/v1/uploads", tags=["uploads"], dependencies=[Depends(limit_writes)])


class UploadCreate(BaseModel):
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    source_kind: Literal["mix", "guitar_stem"] = "mix"


class UploadCreated(BaseModel):
    audio_id: uuid.UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in_s: int


@router.post("", status_code=201)
def create_upload(
    body: UploadCreate,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> UploadCreated:
    audio_type = normalize_declared_type(body.content_type)
    if audio_type is None:
        raise ProblemError(415, "unsupported_media_type", "accepted: MP3, WAV, FLAC, OGG")
    if body.size_bytes > settings.upload_max_bytes:
        raise ProblemError(
            413, "file_too_large", f"maximum size is {settings.upload_max_bytes} bytes"
        )
    quota = settings.daily_upload_quota
    if quota is not None:
        recent = session.execute(
            select(func.count())
            .select_from(AudioAsset)
            .where(
                AudioAsset.user_id == user.id,
                AudioAsset.status != "rejected",
                AudioAsset.created_at > datetime.now(UTC) - timedelta(days=1),
            )
        ).scalar_one()
        if recent >= quota:
            raise ProblemError(
                429,
                "quota_exceeded",
                f"daily limit of {quota} uploads reached",
                headers={"Retry-After": "3600"},
            )

    audio_id = uuid.uuid4()
    asset = AudioAsset(
        id=audio_id,
        user_id=user.id,
        source_kind=body.source_kind,
        content_type=audio_type.value,
        size_bytes=body.size_bytes,
        storage_key=f"audio/{user.id}/{audio_id}",
    )
    session.add(asset)
    url = store.presign_put(
        asset.storage_key, audio_type.value, body.size_bytes, settings.presign_ttl_s
    )
    return UploadCreated(
        audio_id=audio_id,
        upload_url=url,
        headers={"Content-Type": audio_type.value},
        expires_in_s=settings.presign_ttl_s,
    )


@router.post("/{audio_id}/complete", status_code=201)
def complete_upload(
    audio_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> JobOut:
    asset = session.execute(
        select(AudioAsset)
        .where(AudioAsset.id == audio_id, AudioAsset.user_id == user.id)
        .with_for_update()
    ).scalar_one_or_none()
    if asset is None:
        raise ProblemError(404, "not_found", "upload not found")
    if asset.status != "pending_upload":
        raise ProblemError(409, "upload_already_completed", f"upload is {asset.status}")

    info = store.head(asset.storage_key)
    if info is None:
        raise ProblemError(409, "upload_incomplete", "file has not been uploaded yet")

    real_type = sniff_audio_type(store.read_prefix(asset.storage_key, SNIFF_BYTES))
    if info.size_bytes != asset.size_bytes or real_type is None or real_type != asset.content_type:
        store.delete(asset.storage_key)
        asset.status = "rejected"
        session.commit()  # keep the rejection even though the request fails
        raise ProblemError(
            415, "content_type_mismatch", "file content does not match the declared audio type"
        )

    asset.status = "uploaded"
    retention = settings.audio_retention
    # NULL never matches the worker's `expires_at < now()` purge (desktop keeps the audio).
    asset.expires_at = datetime.now(UTC) + retention if retention is not None else None
    job = Job(audio_id=asset.id, status="queued", attempts=0)
    session.add(job)
    session.flush()
    session.refresh(job)
    return JobOut.from_model(job)
