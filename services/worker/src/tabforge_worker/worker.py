"""Worker loop: claim a job, run its stages, store the tab. Stubs in M1 (see pipeline.py)."""

import json
import logging
import os
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from typing import Any

import psycopg

from tabforge_worker import queue
from tabforge_worker.pipeline import STUB_SCORE, Stage, plan_stages

log = logging.getLogger("tabforge_worker")

StageRunner = Callable[[Stage, queue.ClaimedJob], None]


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    database_url: str
    poll_interval_s: float = 2.0
    lease_s: int = 600
    max_attempts: int = 3

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
        )


def stub_stage(stage: Stage, job: queue.ClaimedJob) -> None:
    """M1: no audio processing; the arranging step writes STUB_SCORE."""


def run_once(
    conn: psycopg.Connection[Any],
    config: WorkerConfig,
    run_stage: StageRunner = stub_stage,
    score: dict[str, Any] = STUB_SCORE,
) -> bool:
    """Process at most one job. Returns False when the queue was empty."""
    job = queue.claim_next(conn, config.lease_s, config.max_attempts)
    if job is None:
        return False
    stage: Stage | None = None
    try:
        for stage in plan_stages(job.source_kind):
            queue.set_stage(conn, job.id, stage.value)
            log.info(_event("stage_started", job=job.id, stage=stage.value))
            run_stage(stage, job)
        tab_id = queue.complete(conn, job, score)
    except Exception:
        code = f"{stage.value}_failed" if stage else "pipeline_failed"
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
    log.info(_event("worker_started", lease_s=config.lease_s, max_attempts=config.max_attempts))
    while not stopping:
        try:
            with psycopg.connect(config.database_url, autocommit=True) as conn:
                while not stopping:
                    if not run_once(conn, config):
                        time.sleep(config.poll_interval_s)
        except psycopg.OperationalError:
            log.exception(_event("database_unavailable"))
            time.sleep(config.poll_interval_s)
    return 0
