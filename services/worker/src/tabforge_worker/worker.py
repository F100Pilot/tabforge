"""Worker loop: claim a job, run its stages, store the tab. Stubs in M1 (see pipeline.py)."""

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from types import FrameType
from typing import Any, Literal

import psycopg

from tabforge_worker import queue
from tabforge_worker.pipeline import Pipeline, PipelineError, Stage, StubPipeline

log = logging.getLogger("tabforge_worker")


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    database_url: str
    poll_interval_s: float = 2.0
    lease_s: int = 600
    max_attempts: int = 3
    pipeline: Literal["stub", "real"] = "stub"

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        url = os.environ.get("TABFORGE_DATABASE_URL")
        if not url:
            raise SystemExit("TABFORGE_DATABASE_URL is required")
        return cls(
            database_url=url,
            poll_interval_s=float(os.environ.get("TABFORGE_WORKER_POLL_INTERVAL_S", "2")),
            lease_s=int(os.environ.get("TABFORGE_WORKER_LEASE_S", "600")),
            max_attempts=int(os.environ.get("TABFORGE_WORKER_MAX_ATTEMPTS", "3")),
            pipeline=_pipeline_kind(os.environ.get("TABFORGE_WORKER_PIPELINE", "stub")),
        )


def _pipeline_kind(value: str) -> Literal["stub", "real"]:
    if value == "stub":
        return "stub"
    if value == "real":
        return "real"
    raise SystemExit(f"TABFORGE_WORKER_PIPELINE must be stub or real, got {value!r}")


def build_pipeline(kind: Literal["stub", "real"]) -> Pipeline:
    if kind == "stub":
        return StubPipeline()
    # Heavy ML imports only when the real pipeline is selected (needs the `ml` extra).
    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber
    from tabforge_worker.adapters.demucs import DemucsGuitarSeparator
    from tabforge_worker.adapters.librosa_beats import LibrosaBeatTracker
    from tabforge_worker.adapters.s3_source import S3AudioSource
    from tabforge_worker.real_pipeline import RealPipeline

    return RealPipeline(
        source=S3AudioSource.from_env(),
        transcriber=BasicPitchOnnxTranscriber,
        separator=DemucsGuitarSeparator,
        beat_tracker=LibrosaBeatTracker,
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
    log.info(_event("job_done", job=job.id, tab=tab_id))
    return True


def _event(name: str, **fields: object) -> str:
    """One JSON object per log line; ids only, never user data."""
    return json.dumps({"event": name, **{k: str(v) for k, v in fields.items()}})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    config = WorkerConfig.from_env()
    stopping = False

    def _stop(signum: int, _: FrameType | None) -> None:
        nonlocal stopping
        stopping = True
        log.info(_event("shutdown_requested", signal=signum))

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    pipeline = build_pipeline(config.pipeline)
    log.info(
        _event(
            "worker_started",
            lease_s=config.lease_s,
            max_attempts=config.max_attempts,
            pipeline=config.pipeline,
        )
    )
    while not stopping:
        try:
            with psycopg.connect(config.database_url, autocommit=True) as conn:
                while not stopping:
                    if not run_once(conn, config, pipeline):
                        time.sleep(config.poll_interval_s)
        except psycopg.OperationalError:
            log.exception(_event("database_unavailable"))
            time.sleep(config.poll_interval_s)
    return 0
