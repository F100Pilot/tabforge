"""Worker loop: claim a job, run its stages, store the tab. Stubs in M1 (see pipeline.py).

`main` is the CLI (`python -m tabforge_worker`); the desktop launcher (ADR-0008) runs the same
loop in a thread with `run_forever(config, threading.Event())` and sets the event to stop it.
"""

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Literal, Protocol

import psycopg

from tabforge_worker import queue, retention
from tabforge_worker.pipeline import Pipeline, PipelineError, Stage, StubPipeline

log = logging.getLogger("tabforge_worker")


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    database_url: str
    poll_interval_s: float = 2.0
    lease_s: int = 600
    max_attempts: int = 3
    pipeline: Literal["stub", "real"] = "stub"
    retention_interval_s: float = 3600.0
    # Desktop (ADR-0008): read and delete audio in the API's local storage folder, not S3.
    storage_backend: Literal["s3", "local"] = "s3"
    local_storage_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.storage_backend == "local" and self.local_storage_dir is None:
            raise ValueError("storage_backend=local requires local_storage_dir")

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        url = os.environ.get("TABFORGE_DATABASE_URL")
        if not url:
            raise SystemExit("TABFORGE_DATABASE_URL is required")
        backend = _storage_backend(os.environ.get("TABFORGE_STORAGE_BACKEND", "s3"))
        local_dir = _local_dir(os.environ.get("TABFORGE_LOCAL_STORAGE_DIR"))
        if backend == "local" and local_dir is None:
            raise SystemExit("TABFORGE_LOCAL_STORAGE_DIR is required with storage backend local")
        return cls(
            database_url=url,
            poll_interval_s=float(os.environ.get("TABFORGE_WORKER_POLL_INTERVAL_S", "2")),
            lease_s=int(os.environ.get("TABFORGE_WORKER_LEASE_S", "600")),
            max_attempts=int(os.environ.get("TABFORGE_WORKER_MAX_ATTEMPTS", "3")),
            pipeline=_pipeline_kind(os.environ.get("TABFORGE_WORKER_PIPELINE", "stub")),
            retention_interval_s=float(os.environ.get("TABFORGE_WORKER_RETENTION_S", "3600")),
            storage_backend=backend,
            local_storage_dir=local_dir,
        )


def _pipeline_kind(value: str) -> Literal["stub", "real"]:
    if value == "stub":
        return "stub"
    if value == "real":
        return "real"
    raise SystemExit(f"TABFORGE_WORKER_PIPELINE must be stub or real, got {value!r}")


def _storage_backend(value: str) -> Literal["s3", "local"]:
    if value == "s3":
        return "s3"
    if value == "local":
        return "local"
    raise SystemExit(f"TABFORGE_STORAGE_BACKEND must be s3 or local, got {value!r}")


def _local_dir(value: str | None) -> Path | None:
    return Path(value) if value else None


class AudioStore(Protocol):
    """Where uploaded audio lives: read by the real pipeline, deleted by retention."""

    def download(self, key: str, dst: Path) -> None: ...
    def delete(self, key: str) -> None: ...


def build_store(config: WorkerConfig) -> AudioStore:
    if config.storage_backend == "local":
        from tabforge_worker.adapters.local_source import LocalAudioSource

        if config.local_storage_dir is None:  # guarded by WorkerConfig; narrows the type
            raise SystemExit("TABFORGE_LOCAL_STORAGE_DIR is required with storage_backend=local")
        return LocalAudioSource(config.local_storage_dir)
    from tabforge_worker.adapters.s3_source import S3AudioSource

    return S3AudioSource.from_env()


def build_pipeline(kind: Literal["stub", "real"], source: AudioStore | None = None) -> Pipeline:
    if kind == "stub":
        return StubPipeline()
    # Heavy ML imports only when the real pipeline is selected (needs the `ml` extra).
    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber
    from tabforge_worker.adapters.demucs import DemucsGuitarSeparator
    from tabforge_worker.adapters.librosa_beats import LibrosaBeatTracker
    from tabforge_worker.adapters.s3_source import S3AudioSource
    from tabforge_worker.adapters.stereo import StereoSideAnalyzer
    from tabforge_worker.real_pipeline import RealPipeline

    return RealPipeline(
        source=source or S3AudioSource.from_env(),
        transcriber=BasicPitchOnnxTranscriber,
        separator=DemucsGuitarSeparator,
        beat_tracker=LibrosaBeatTracker,
        stereo=StereoSideAnalyzer,
    )


def run_once(conn: psycopg.Connection[Any], config: WorkerConfig, pipeline: Pipeline) -> bool:
    """Process at most one job. Returns False when the queue was empty."""
    job = queue.claim_next(conn, config.lease_s, config.max_attempts)
    if job is None:
        return False
    current: list[Stage] = []

    def on_stage(stage: Stage) -> None:
        current.append(stage)
        queue.set_stage(conn, job.id, stage.value)
        log.info(_event("stage_started", job=job.id, stage=stage.value))

    try:
        result = pipeline.process(job, on_stage)
        tab_id = queue.complete(conn, job, result.score, result.duration_ms, result.sha256)
    except PipelineError as exc:
        log.warning(_event("job_failed", job=job.id, error_code=exc.code))
        queue.fail(conn, job.id, exc.code)
        return True
    except Exception:
        code = f"{current[-1].value}_failed" if current else "pipeline_failed"
        log.exception(_event("job_failed", job=job.id, error_code=code))
        queue.fail(conn, job.id, code)
        return True
    if tab_id is None:
        log.info(_event("job_gone", job=job.id))  # owner deleted their account mid-job
        return True
    log.info(_event("job_done", job=job.id, tab=tab_id))
    return True


def _event(name: str, **fields: object) -> str:
    """One JSON object per log line; ids only, never user data."""
    return json.dumps({"event": name, **{k: str(v) for k, v in fields.items()}})


class StopFlag(Protocol):
    """What `run_forever` polls; `threading.Event` fits."""

    def is_set(self) -> bool: ...
    def wait(self, timeout: float) -> bool: ...


class _SignalFlag:
    """The CLI's stop flag. A plain attribute, because a signal handler must not take a lock:
    `Event.set()` deadlocks if the signal lands while this thread holds the Event's own lock.
    """

    def __init__(self) -> None:
        self._set = False

    def set(self) -> None:
        self._set = True

    def is_set(self) -> bool:
        return self._set

    def wait(self, timeout: float) -> bool:
        time.sleep(timeout)
        return self._set


def run_forever(
    config: WorkerConfig,
    stop: StopFlag,
    pipeline: Pipeline | None = None,
    store: AudioStore | None = None,
) -> None:
    """Claim jobs and purge retention until `stop` is set; reconnects if Postgres drops.

    Safe to run in a thread: no signal handling and no logging setup here (see `main`). A job in
    progress finishes before the loop checks `stop` again.
    """
    store = store or build_store(config)
    pipeline = pipeline or build_pipeline(config.pipeline, store)
    next_purge = 0.0
    log.info(
        _event(
            "worker_started",
            lease_s=config.lease_s,
            max_attempts=config.max_attempts,
            pipeline=config.pipeline,
        )
    )
    while not stop.is_set():
        try:
            with psycopg.connect(config.database_url, autocommit=True) as conn:
                while not stop.is_set():
                    if time.monotonic() >= next_purge:
                        purged = retention.purge_expired(conn, store)
                        auth_purged = retention.purge_auth(conn)
                        log.info(_event("retention_run", purged=purged, auth_purged=auth_purged))
                        next_purge = time.monotonic() + config.retention_interval_s
                    if not run_once(conn, config, pipeline):
                        stop.wait(config.poll_interval_s)
        except psycopg.OperationalError:
            log.exception(_event("database_unavailable"))
            stop.wait(config.poll_interval_s)
    log.info(_event("worker_stopped"))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    config = WorkerConfig.from_env()
    stop = _SignalFlag()

    def _stop(signum: int, _: FrameType | None) -> None:
        stop.set()
        log.info(_event("shutdown_requested", signal=signum))

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_forever(config, stop)
    return 0
