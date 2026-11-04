"""Job queue on Postgres with FOR UPDATE SKIP LOCKED (ADR-0001).

A job is leased by setting locked_at; stages refresh it. A `running` job whose lease
expired (worker crashed) is claimed again, until it has used `max_attempts`.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

MAX_ATTEMPTS_ERROR = "max_attempts_exceeded"

_CLAIM = """
WITH next AS (
    SELECT j.id
    FROM jobs j
    WHERE j.status = 'queued'
       OR (j.status = 'running' AND j.locked_at < now() - make_interval(secs => %(lease_s)s))
    ORDER BY j.created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE jobs
SET status = 'running', stage = NULL, error_code = NULL,
    attempts = jobs.attempts + 1, locked_at = now(), updated_at = now()
FROM next, audio_assets a
WHERE jobs.id = next.id AND a.id = jobs.audio_id
RETURNING jobs.id, jobs.audio_id, jobs.attempts, a.source_kind, a.user_id
"""


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: uuid.UUID
    audio_id: uuid.UUID
    attempts: int
    source_kind: str
    owner_id: uuid.UUID


def claim_next(conn: psycopg.Connection[Any], lease_s: int, max_attempts: int) -> ClaimedJob | None:
    """Lease the oldest runnable job, or return None. Jobs over the attempt limit fail."""
    while True:
        with conn.transaction():
            row = conn.execute(_CLAIM, {"lease_s": lease_s}).fetchone()
            if row is None:
                return None
            job = ClaimedJob(*row)
            if job.attempts <= max_attempts:
                return job
            _fail(conn, job.id, MAX_ATTEMPTS_ERROR)


def set_stage(conn: psycopg.Connection[Any], job_id: uuid.UUID, stage: str) -> None:
    """Record the current stage and renew the lease."""
    with conn.transaction():
        conn.execute(
            "UPDATE jobs SET stage = %s, locked_at = now(), updated_at = now() "
            "WHERE id = %s AND status = 'running'",
            (stage, job_id),
        )


def complete(conn: psycopg.Connection[Any], job: ClaimedJob, score: dict[str, Any]) -> uuid.UUID:
    """Store the generated tab and its first revision, and mark the job done (one transaction)."""
    title = f"Transcrição {datetime.now(UTC):%Y-%m-%d}"
    with conn.transaction():
        tab_id = _scalar(
            conn,
            "INSERT INTO tabs (owner_id, title) VALUES (%s, %s) RETURNING id",
            (job.owner_id, title),
        )
        revision_id = _scalar(
            conn,
            "INSERT INTO tab_revisions (tab_id, score, source) "
            "VALUES (%s, %s::jsonb, 'ai') RETURNING id",
            (tab_id, json.dumps(score)),
        )
        conn.execute(
            "UPDATE tabs SET current_revision_id = %s WHERE id = %s", (revision_id, tab_id)
        )
        conn.execute(
            "UPDATE jobs SET status = 'done', tab_id = %s, locked_at = NULL, updated_at = now() "
            "WHERE id = %s",
            (tab_id, job.id),
        )
    return tab_id


def fail(conn: psycopg.Connection[Any], job_id: uuid.UUID, error_code: str) -> None:
    with conn.transaction():
        _fail(conn, job_id, error_code)


def _fail(conn: psycopg.Connection[Any], job_id: uuid.UUID, error_code: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'failed', error_code = %s, locked_at = NULL, updated_at = now() "
        "WHERE id = %s",
        (error_code, job_id),
    )


def _scalar(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> uuid.UUID:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise RuntimeError("INSERT ... RETURNING returned no row")
    value: uuid.UUID = row[0]
    return value
