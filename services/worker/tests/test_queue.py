import uuid
from typing import Any

import psycopg
import pytest

from tabforge_worker import queue
from tabforge_worker.pipeline import STUB_SCORE, Stage
from tabforge_worker.worker import WorkerConfig, run_once

pytestmark = pytest.mark.db

Conn = psycopg.Connection[Any]


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
        ("guitar_stem", [Stage.TRANSCRIBING, Stage.ARRANGING]),
        ("mix", [Stage.SEPARATING, Stage.TRANSCRIBING, Stage.ARRANGING]),
    ],
)
def test_run_once_runs_planned_stages_and_stores_tab(
    conn: Conn, database_url: str, source_kind: str, expected: list[Stage]
) -> None:
    job_id = _job(conn, source_kind)
    seen: list[Stage] = []

    assert run_once(conn, WorkerConfig(database_url), lambda stage, _: seen.append(stage))

    assert seen == expected
    status, stage, attempts, error, tab_id = _job_row(conn, job_id)
    assert (status, stage, attempts, error) == ("done", "arranging", 1, None)
    tab = conn.execute(
        "SELECT t.owner_id = a.user_id, t.visibility, r.source, r.score "
        "FROM tabs t JOIN tab_revisions r ON r.id = t.current_revision_id "
        "JOIN jobs j ON j.tab_id = t.id JOIN audio_assets a ON a.id = j.audio_id "
        "WHERE t.id = %s",
        (tab_id,),
    ).fetchone()
    assert tab == (True, "private", "ai", STUB_SCORE)


def test_stage_error_marks_job_failed_with_stage_code(conn: Conn, database_url: str) -> None:
    job_id = _job(conn, "mix")

    def boom(stage: Stage, _: queue.ClaimedJob) -> None:
        if stage is Stage.TRANSCRIBING:
            raise RuntimeError("model crashed")

    assert run_once(conn, WorkerConfig(database_url), boom)
    status, stage, _, error, tab_id = _job_row(conn, job_id)
    assert (status, stage, error, tab_id) == ("failed", "transcribing", "transcribing_failed", None)
    assert conn.execute("SELECT count(*) FROM tabs").fetchone() == (0,)


def test_run_once_on_empty_queue_returns_false(conn: Conn, database_url: str) -> None:
    assert run_once(conn, WorkerConfig(database_url)) is False
