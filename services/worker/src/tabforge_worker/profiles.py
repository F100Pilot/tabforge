"""Fretting profiles on Postgres (ADR-0011): refresh the stale ones, read a user's weights.

The API marks a profile `stale` (and sets `requested_at`) whenever the user's training data
changes. `refresh_next` claims one with FOR UPDATE SKIP LOCKED while it loads the training data,
then tunes without holding the lock, so an API request that marks the profile again never waits
for the grid search. The result is written in any case; if the profile was marked again in the
meantime (`requested_at` changed), it stays `stale` and is refreshed again on the next run.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from tabforge_worker.arrange.fretting import Weights
from tabforge_worker.learning import (
    ReferenceRow,
    RevisionRow,
    TrainingTrack,
    TuningResult,
    build_training_set,
    tune,
    weights_from_json,
    weights_to_json,
)

MAX_ROWS = 800  # newest references (one per track) / edited tabs read per refresh

_CLAIM = """
SELECT user_id, requested_at FROM fretting_profiles
WHERE status = 'stale'
ORDER BY requested_at NULLS FIRST, user_id
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

# The tuning of the tab's own track, when the reference's notes do not show it for a string.
_REFERENCES = """
SELECT r.tab_id, r.track_index, r.notes,
       COALESCE(v.score -> 'tracks' -> r.track_index -> 'tuning', v.score -> 'tuning')
FROM tab_references r
JOIN tabs t ON t.id = r.tab_id
LEFT JOIN tab_revisions v ON v.id = t.current_revision_id
WHERE t.owner_id = %s
ORDER BY t.created_at DESC, t.id, r.track_index
LIMIT %s
"""

# Tabs without a reference: latest user revision and first AI revision.
_REVISIONS = """
SELECT t.id,
       (SELECT v.score FROM tab_revisions v WHERE v.tab_id = t.id AND v.source = 'user'
        ORDER BY v.created_at DESC, v.id DESC LIMIT 1),
       (SELECT v.score FROM tab_revisions v WHERE v.tab_id = t.id AND v.source = 'ai'
        ORDER BY v.created_at, v.id LIMIT 1)
FROM tabs t
WHERE t.owner_id = %s
  AND EXISTS (SELECT 1 FROM tab_revisions v WHERE v.tab_id = t.id AND v.source = 'user')
  AND NOT EXISTS (SELECT 1 FROM tab_references r WHERE r.tab_id = t.id)
ORDER BY t.created_at DESC, t.id
LIMIT %s
"""

_SAVE = """
UPDATE fretting_profiles
SET status = CASE WHEN requested_at IS NOT DISTINCT FROM %(claimed)s
                  THEN %(status)s ELSE 'stale' END,
    weights = %(weights)s, default_accuracy = %(default_accuracy)s,
    tuned_accuracy = %(tuned_accuracy)s, tabs = %(tabs)s, notes = %(notes)s, updated_at = now()
WHERE user_id = %(user_id)s
RETURNING status
"""


@dataclass(frozen=True, slots=True)
class Refreshed:
    user_id: uuid.UUID
    result: TuningResult
    status: str | None  # as stored: the result's, or "stale" if marked again; None if gone
    seconds: float  # time spent tuning


class TuningError(Exception):
    """Tuning one profile failed (not a database problem); the caller can postpone it."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"tuning failed for {user_id}")
        self.user_id = user_id


def load_training_set(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> list[TrainingTrack]:
    references = [
        ReferenceRow(str(tab), index, notes, tuning)
        for tab, index, notes, tuning in conn.execute(_REFERENCES, (user_id, MAX_ROWS))
    ]
    revisions = [
        RevisionRow(str(tab), edited, generated)
        for tab, edited, generated in conn.execute(_REVISIONS, (user_id, MAX_ROWS))
    ]
    return build_training_set(references, revisions)


def save_result(
    conn: psycopg.Connection[Any],
    user_id: uuid.UUID,
    claimed: datetime | None,
    result: TuningResult,
) -> str | None:
    """Store a result; returns the stored status (None if the profile no longer exists)."""
    row = conn.execute(
        _SAVE,
        {
            "claimed": claimed,
            "status": result.status,
            "weights": None if result.weights is None else Jsonb(weights_to_json(result.weights)),
            "default_accuracy": result.default_accuracy,
            "tuned_accuracy": result.tuned_accuracy,
            "tabs": result.tabs,
            "notes": result.notes,
            "user_id": user_id,
        },
    ).fetchone()
    return None if row is None else str(row[0])


def refresh_next(conn: psycopg.Connection[Any]) -> Refreshed | None:
    """Tune the stale profile waiting longest; None when there is none.

    Database errors propagate as they are; any other failure raises `TuningError`.
    """
    with conn.transaction():
        row = conn.execute(_CLAIM).fetchone()
        if row is None:
            return None
        user_id, claimed = row
        try:
            tracks = load_training_set(conn, user_id)
        except psycopg.Error:
            raise
        except Exception as exc:
            raise TuningError(user_id) from exc
    started = time.perf_counter()
    try:
        result = tune(tracks)
    except Exception as exc:
        raise TuningError(user_id) from exc
    seconds = time.perf_counter() - started
    with conn.transaction():
        status = save_result(conn, user_id, claimed, result)
    return Refreshed(user_id, result, status, seconds)


def postpone(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> None:
    """Send a profile that failed to the back of the queue, so it does not block the others."""
    with conn.transaction():
        conn.execute(
            "UPDATE fretting_profiles SET requested_at = now() "
            "WHERE user_id = %s AND status = 'stale'",
            (user_id,),
        )


def accepted_weights(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> Weights | None:
    """The user's tuned weights while they are in use (profile ready, weights accepted)."""
    row = conn.execute(
        "SELECT weights FROM fretting_profiles "
        "WHERE user_id = %s AND status = 'ready' AND weights IS NOT NULL",
        (user_id,),
    ).fetchone()
    return None if row is None else weights_from_json(row[0])
