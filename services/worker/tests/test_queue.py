import logging
import uuid
from typing import Any

import psycopg
import pytest

from tabforge_worker import queue
from tabforge_worker.pipeline import (
    STUB_SCORE,
    PipelineError,
    PipelineResult,
    Stage,
    StageCallback,
    StubPipeline,
    plan_stages,
)
from tabforge_worker.worker import WorkerConfig, run_once

pytestmark = pytest.mark.db

Conn = psycopg.Connection[Any]


class RecordingPipeline:
    """Reports the planned stages, optionally failing at one of them."""

    def __init__(self, fail_at: Stage | None = None, error: Exception | None = None) -> None:
        self.seen: list[Stage] = []
        self.fail_at = fail_at
        self.error = error or RuntimeError("model crashed")

    def process(self, job: queue.ClaimedJob, on_stage: StageCallback) -> PipelineResult:
        for stage in plan_stages(job.source_kind):
            on_stage(stage)
            self.seen.append(stage)
            if stage is self.fail_at:
                raise self.error
        return PipelineResult(STUB_SCORE, duration_ms=1234, sha256="ab" * 32)


def _user(conn: Conn) -> uuid.UUID:
    row = conn.execute(
        "INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@example.com",)
    ).fetchone()
    assert row is not None
    user_id: uuid.UUID = row[0]
    return user_id


def _job(conn: Conn, source_kind: str = "guitar_stem", age_s: int = 0) -> uuid.UUID:
    audio = conn.execute(
        "INSERT INTO audio_assets (user_id, status, source_kind, content_type, size_bytes, "
        "storage_key) VALUES (%s, 'uploaded', %s, 'audio/wav', 10, %s) RETURNING id",
        (_user(conn), source_kind, f"audio/{uuid.uuid4()}"),
    ).fetchone()
    assert audio is not None
    row = conn.execute(
        "INSERT INTO jobs (audio_id, created_at) "
        "VALUES (%s, now() - make_interval(secs => %s)) RETURNING id",
        (audio[0], age_s),
    ).fetchone()
    assert row is not None
    job_id: uuid.UUID = row[0]
    return job_id


def _job_row(conn: Conn, job_id: uuid.UUID) -> tuple[Any, ...]:
    row = conn.execute(
        "SELECT status, stage, attempts, error_code, tab_id FROM jobs WHERE id = %s", (job_id,)
    ).fetchone()
    assert row is not None
    return tuple(row)


def test_claims_oldest_queued_job_and_increments_attempts(conn: Conn) -> None:
    newer = _job(conn, age_s=0)
    older = _job(conn, age_s=60)
    job = queue.claim_next(conn, lease_s=600, max_attempts=3)
    assert job is not None
    assert (job.id, job.attempts) == (older, 1)
    assert _job_row(conn, older)[:3] == ("running", None, 1)
    assert _job_row(conn, newer)[0] == "queued"


def test_empty_queue_returns_none(conn: Conn) -> None:
    assert queue.claim_next(conn, lease_s=600, max_attempts=3) is None


def test_row_locked_by_another_worker_is_skipped(conn: Conn, database_url: str) -> None:
    first = _job(conn, age_s=60)
    second = _job(conn, age_s=0)
    with psycopg.connect(database_url) as other:  # holds a lock on `first`, as a worker would
        other.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (first,))
        job = queue.claim_next(conn, lease_s=600, max_attempts=3)
        assert job is not None
        assert job.id == second
        other.rollback()


def test_expired_lease_is_reclaimed(conn: Conn) -> None:
    job_id = _job(conn)
    assert queue.claim_next(conn, lease_s=600, max_attempts=3) is not None
    conn.execute(
        "UPDATE jobs SET locked_at = now() - interval '11 minutes' WHERE id = %s", (job_id,)
    )
    job = queue.claim_next(conn, lease_s=600, max_attempts=3)
    assert job is not None
    assert (job.id, job.attempts) == (job_id, 2)


def test_live_lease_is_not_reclaimed(conn: Conn) -> None:
    _job(conn)
    assert queue.claim_next(conn, lease_s=600, max_attempts=3) is not None
    assert queue.claim_next(conn, lease_s=600, max_attempts=3) is None


def test_job_over_attempt_limit_fails(conn: Conn) -> None:
    job_id = _job(conn)
    conn.execute(
        "UPDATE jobs SET status = 'running', attempts = 3, "
        "locked_at = now() - interval '1 hour' WHERE id = %s",
        (job_id,),
    )
    assert queue.claim_next(conn, lease_s=600, max_attempts=3) is None
    assert _job_row(conn, job_id)[0::3] == ("failed", queue.MAX_ATTEMPTS_ERROR)


@pytest.mark.parametrize(
    ("source_kind", "expected"),
    [
        ("guitar_stem", [Stage.NORMALIZING, Stage.TRANSCRIBING, Stage.ARRANGING]),
        ("mix", [Stage.NORMALIZING, Stage.SEPARATING, Stage.TRANSCRIBING, Stage.ARRANGING]),
    ],
)
def test_run_once_runs_planned_stages_and_stores_tab(
    conn: Conn, database_url: str, source_kind: str, expected: list[Stage]
) -> None:
    job_id = _job(conn, source_kind)
    pipeline = RecordingPipeline()

    assert run_once(conn, WorkerConfig(database_url), pipeline)

    assert pipeline.seen == expected
    status, stage, attempts, error, tab_id = _job_row(conn, job_id)
    assert (status, stage, attempts, error) == ("done", "arranging", 1, None)
    tab = conn.execute(
        "SELECT t.owner_id = a.user_id, t.visibility, r.source, r.score, a.duration_ms, a.sha256 "
        "FROM tabs t JOIN tab_revisions r ON r.id = t.current_revision_id "
        "JOIN jobs j ON j.tab_id = t.id JOIN audio_assets a ON a.id = j.audio_id "
        "WHERE t.id = %s",
        (tab_id,),
    ).fetchone()
    assert tab == (True, "private", "ai", STUB_SCORE, 1234, "ab" * 32)


def test_claim_returns_storage_key_and_type(conn: Conn) -> None:
    _job(conn)
    job = queue.claim_next(conn, lease_s=600, max_attempts=3)
    assert job is not None
    assert job.storage_key.startswith("audio/")
    assert job.content_type == "audio/wav"


def test_stage_error_marks_job_failed_with_stage_code(conn: Conn, database_url: str) -> None:
    job_id = _job(conn, "mix")
    assert run_once(conn, WorkerConfig(database_url), RecordingPipeline(Stage.TRANSCRIBING))
    status, stage, _, error, tab_id = _job_row(conn, job_id)
    assert (status, stage, error, tab_id) == ("failed", "transcribing", "transcribing_failed", None)
    assert conn.execute("SELECT count(*) FROM tabs").fetchone() == (0,)


def test_pipeline_error_code_is_stored(conn: Conn, database_url: str) -> None:
    job_id = _job(conn)
    pipe = RecordingPipeline(Stage.NORMALIZING, PipelineError("audio_too_long"))
    assert run_once(conn, WorkerConfig(database_url), pipe)
    assert _job_row(conn, job_id)[0::3] == ("failed", "audio_too_long")


def test_run_once_on_empty_queue_returns_false(conn: Conn, database_url: str) -> None:
    assert run_once(conn, WorkerConfig(database_url), StubPipeline()) is False


class DeletingPipeline(RecordingPipeline):
    """The owner deletes their account (DELETE /v1/me) while the job is being processed."""

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self.database_url = database_url

    def process(self, job: queue.ClaimedJob, on_stage: StageCallback) -> PipelineResult:
        result = super().process(job, on_stage)
        with psycopg.connect(self.database_url, autocommit=True) as other:
            other.execute("DELETE FROM users WHERE id = %s", (job.owner_id,))
        return result


def test_complete_is_a_noop_when_the_owner_was_deleted(conn: Conn) -> None:
    _job(conn)
    job = queue.claim_next(conn, lease_s=600, max_attempts=3)
    assert job is not None
    conn.execute("DELETE FROM users WHERE id = %s", (job.owner_id,))
    assert queue.complete(conn, job, STUB_SCORE) is None
    assert conn.execute("SELECT count(*) FROM tabs").fetchone() == (0,)


def test_run_once_survives_account_deletion_mid_job(
    conn: Conn, database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    _job(conn)
    with caplog.at_level(logging.INFO, logger="tabforge_worker"):
        assert run_once(conn, WorkerConfig(database_url), DeletingPipeline(database_url))
    assert '"job_gone"' in caplog.text
    assert "job_failed" not in caplog.text
    assert conn.execute("SELECT count(*) FROM jobs").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM tabs").fetchone() == (0,)


def test_complete_names_the_tab_after_the_score_tuning(conn: Conn) -> None:
    _job(conn)
    job = queue.claim_next(conn, lease_s=600, max_attempts=3)
    assert job is not None
    score = {**STUB_SCORE, "tuning": [62, 57, 53, 48, 43, 38]}  # D standard
    tab_id = queue.complete(conn, job, score)
    assert conn.execute("SELECT tuning FROM tabs WHERE id = %s", (tab_id,)).fetchone() == (
        "D standard",
    )
