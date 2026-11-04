"""Audio retention (PRD §5): delete originals past `expires_at` and abandoned uploads.
Also drops expired login tokens and sessions (US-07), which are useless once expired.

Rows are claimed with FOR UPDATE SKIP LOCKED so several workers never purge the same object.
A storage error leaves the row untouched for the next run; S3 deletes are idempotent, so an
upload that never reached storage is cleaned the same way.
"""

import logging
from typing import Any, Protocol

import psycopg

log = logging.getLogger("tabforge_worker")
BATCH = 100

_CANDIDATES = """
SELECT id, storage_key FROM audio_assets
WHERE (status = 'uploaded' AND expires_at < now())
   OR (status = 'pending_upload' AND created_at < now() - interval '1 day')
ORDER BY created_at
LIMIT %s
FOR UPDATE SKIP LOCKED
"""


class ObjectDeleter(Protocol):
    def delete(self, key: str) -> None: ...


def purge_expired(conn: psycopg.Connection[Any], store: ObjectDeleter, batch: int = BATCH) -> int:
    """Delete up to `batch` expired objects; return how many were purged."""
    purged = 0
    with conn.transaction():
        for audio_id, key in conn.execute(_CANDIDATES, (batch,)).fetchall():
            try:
                store.delete(key)
            except Exception:
                log.exception('{"event": "retention_delete_failed", "audio": "%s"}', audio_id)
                continue
            conn.execute("UPDATE audio_assets SET status = 'expired' WHERE id = %s", (audio_id,))
            purged += 1
    return purged


def purge_auth(conn: psycopg.Connection[Any]) -> int:
    """Delete expired login tokens and sessions; return how many rows went."""
    with conn.transaction():
        tokens = conn.execute("DELETE FROM login_tokens WHERE expires_at < now()").rowcount
        sessions = conn.execute("DELETE FROM sessions WHERE expires_at < now()").rowcount
    return tokens + sessions
