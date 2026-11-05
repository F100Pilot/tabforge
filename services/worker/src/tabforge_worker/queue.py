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

from tabforge_worker.arrange.fretting import Weights

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
RETURNING jobs.id, jobs.audio_id, jobs.attempts, a.source_kind, a.user_id,
          a.storage_key, a.content_type
"""


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: uuid.UUID
    audio_id: uuid.UUID
    attempts: int
    source_kind: str
    owner_id: uuid.UUID
    storage_key: str
    content_type: str
    # The owner's tuned string/fret weights (ADR-0011), set by the worker loop; None = default.
    weights: Weights | None = None


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


def complete(
    conn: psycopg.Connection[Any],
    job: ClaimedJob,
    score: dict[str, Any],
    duration_ms: int | None = None,
    sha256: str | None = None,
) -> uuid.UUID | None:
    """Store the generated tab and its first revision, and mark the job done (one transaction).

    Returns None, storing nothing, when the owner deleted their account meanwhile (US-07): the
    job is gone with them. KEY SHARE on the user row orders this against a concurrent delete
    (which waits, then cascades to the new tab) instead of deadlocking on the tab's foreign key.
    """
    title = f"Transcrição {datetime.now(UTC):%Y-%m-%d}"
    with conn.transaction():
        owner = conn.execute(
            "SELECT 1 FROM users u JOIN audio_assets a ON a.user_id = u.id "
            "JOIN jobs j ON j.audio_id = a.id WHERE j.id = %s FOR KEY SHARE OF u",
            (job.id,),
        ).fetchone()
        if owner is None:
            return None
        conn.execute(
            "UPDATE audio_assets SET duration_ms = COALESCE(%s, duration_ms), "
            "sha256 = COALESCE(%s, sha256) WHERE id = %s",
            (duration_ms, sha256, job.audio_id),
        )
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
