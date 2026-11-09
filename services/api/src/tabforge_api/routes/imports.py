"""Import a song from a YouTube link (desktop only, ADR-0014).

The API downloads the audio as MP3 with yt-dlp, stores it like a finished upload and queues
the transcription job. A copy of the MP3 is kept in the user's music folder. Plain `def`: the
download (up to a few minutes) runs in Starlette's thread pool, not on the event loop.
"""

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tabforge_api import youtube
from tabforge_api.audio_types import SNIFF_BYTES, AudioType, sniff_audio_type
from tabforge_api.deps import CurrentUser, SessionDep, SettingsDep, StoreDep, limit_writes
from tabforge_api.local_storage import LocalObjectStore
from tabforge_api.models import AudioAsset, Job
from tabforge_api.problems import ProblemError
from tabforge_api.routes.jobs import JobOut

router = APIRouter(prefix="/v1/imports", tags=["imports"], dependencies=[Depends(limit_writes)])

_STATUS = {"audio_too_long": 422, "download_failed": 502, "unavailable": 501}


class YoutubeImportIn(BaseModel):
    url: str = Field(max_length=youtube.MAX_URL_LENGTH)
    source_kind: Literal["mix", "guitar_stem"] = "mix"


class YoutubeImportOut(BaseModel):
    job: JobOut
    title: str
    mp3_path: str | None  # the copy in the music folder, when one is configured


def _keep_copy(source: Path, folder: Path, title: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stem = youtube.safe_filename(title)
    target = folder / f"{stem}.mp3"
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}).mp3"
        n += 1
    shutil.copyfile(source, target)
    return target


@router.post("/youtube", status_code=201)
def import_youtube(
    body: YoutubeImportIn,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> YoutubeImportOut:
    if not youtube.is_youtube_url(body.url):
        raise ProblemError(422, "invalid_youtube_url", "paste a link to a YouTube video")
    if not isinstance(store, LocalObjectStore):  # only registered in desktop (local storage)
        raise ProblemError(404, "not_found", "not available")

    with tempfile.TemporaryDirectory(prefix="tabforge-youtube-") as tmp:
        try:
            got = youtube.download_mp3(
                body.url.strip(),
                Path(tmp),
                ffmpeg=settings.ffmpeg,
                node=settings.node,
                max_duration_s=settings.max_audio_duration_s,
            )
        except youtube.YoutubeError as exc:
            raise ProblemError(_STATUS.get(exc.code, 502), exc.code, exc.detail) from exc

        size = got.path.stat().st_size
        if size > settings.upload_max_bytes:
            raise ProblemError(
                413, "file_too_large", f"maximum size is {settings.upload_max_bytes} bytes"
            )
        with got.path.open("rb") as fh:
            if sniff_audio_type(fh.read(SNIFF_BYTES)) is not AudioType.MP3:
                raise ProblemError(502, "download_failed", "the converted file is not MP3")

        audio_id = uuid.uuid4()
        asset = AudioAsset(
            id=audio_id,
            user_id=user.id,
            source_kind=body.source_kind,
            content_type=AudioType.MP3.value,
            size_bytes=size,
            storage_key=f"audio/{user.id}/{audio_id}",
            status="uploaded",
            expires_at=None,  # desktop keeps the audio until the user deletes it
        )
        store.put_file(asset.storage_key, got.path)
        copy = _keep_copy(got.path, settings.music_dir, got.title) if settings.music_dir else None

    session.add(asset)
    job = Job(audio_id=audio_id, status="queued", attempts=0)
    session.add(job)
    session.flush()
    session.refresh(job)
    return YoutubeImportOut(
        job=JobOut.from_model(job), title=got.title, mp3_path=str(copy) if copy else None
    )
