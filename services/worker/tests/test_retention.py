import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tabforge_worker.adapters.local_source import LocalAudioSource, key_path
from tabforge_worker.retention import purge_auth, purge_expired

pytestmark = pytest.mark.db

Conn = psycopg.Connection[Any]


class FakeStore:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.deleted: list[str] = []
        self.fail_on = fail_on or set()

    def delete(self, key: str) -> None:
        if key in self.fail_on:
            raise RuntimeError("s3 down")
        self.deleted.append(key)


def _asset(conn: Conn, status: str, expires_in: str | None, created_ago: str = "0 s") -> str:
    """`expires_in` / `created_ago` are Postgres intervals, e.g. '-1 day', '25 hours'."""
    user = conn.execute(
        "INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@x.y",)
    ).fetchone()
    assert user is not None
    key = f"audio/{uuid.uuid4()}"
    conn.execute(
        "INSERT INTO audio_assets (user_id, status, source_kind, content_type, size_bytes, "
        "storage_key, expires_at, created_at) VALUES (%s, %s, 'mix', 'audio/wav', 10, %s, "
        "now() + %s::interval, now() - %s::interval)",
        (user[0], status, key, expires_in, created_ago),
    )
    return key


def _status(conn: Conn, key: str) -> str:
    row = conn.execute("SELECT status FROM audio_assets WHERE storage_key = %s", (key,)).fetchone()
    assert row is not None
    value: str = row[0]
    return value


def test_expired_uploads_are_deleted_and_marked(conn: Conn) -> None:
    old = _asset(conn, "uploaded", "-1 day")
    fresh = _asset(conn, "uploaded", "29 days")
    store = FakeStore()
    assert purge_expired(conn, store) == 1
    assert store.deleted == [old]
    assert (_status(conn, old), _status(conn, fresh)) == ("expired", "uploaded")


def test_abandoned_pending_uploads_are_cleaned_after_a_day(conn: Conn) -> None:
    stale = _asset(conn, "pending_upload", None, "25 hours")
    recent = _asset(conn, "pending_upload", None, "1 hour")
    store = FakeStore()
    assert purge_expired(conn, store) == 1
    assert store.deleted == [stale]
    assert (_status(conn, stale), _status(conn, recent)) == ("expired", "pending_upload")


def test_storage_failure_leaves_the_row_for_the_next_run(conn: Conn) -> None:
    key = _asset(conn, "uploaded", "-1 day")
    assert purge_expired(conn, FakeStore(fail_on={key})) == 0
    assert _status(conn, key) == "uploaded"


def test_rejected_and_expired_rows_are_left_alone(conn: Conn) -> None:
    _asset(conn, "rejected", None, "40 days")
    _asset(conn, "expired", "-40 days")
    store = FakeStore()
    assert purge_expired(conn, store) == 0
    assert store.deleted == []


def test_purge_auth_removes_expired_login_tokens_and_sessions(conn: Conn) -> None:
    user = conn.execute("INSERT INTO users (email) VALUES ('a@x.y') RETURNING id").fetchone()
    assert user is not None
    for name, expires in (("old", "-1 second"), ("live", "10 minutes")):
        conn.execute(
            "INSERT INTO login_tokens (email, token_hash, expires_at) "
            "VALUES ('a@x.y', %s, now() + %s::interval)",
            (f"tok-{name}", expires),
        )
        conn.execute(
            "INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at) "
            "VALUES (%s, %s, 'c', now() + %s::interval)",
            (user[0], f"ses-{name}", expires),
        )
    assert purge_auth(conn) == 2
    assert conn.execute("SELECT token_hash FROM login_tokens").fetchall() == [("tok-live",)]
    assert conn.execute("SELECT token_hash FROM sessions").fetchall() == [("ses-live",)]


def test_local_storage_files_are_deleted(conn: Conn, tmp_path: Path) -> None:
    # Desktop (ADR-0008): the same purge, through the local source.
    old = _asset(conn, "uploaded", "-1 day")
    fresh = _asset(conn, "uploaded", "29 days")
    for key in (old, fresh):
        path = key_path(tmp_path, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFF")
    assert purge_expired(conn, LocalAudioSource(tmp_path)) == 1
    assert not key_path(tmp_path, old).exists()
    assert key_path(tmp_path, fresh).exists()
    assert _status(conn, old) == "expired"


def test_local_file_already_gone_is_still_marked_expired(conn: Conn, tmp_path: Path) -> None:
    key = _asset(conn, "uploaded", "-1 day")
    assert purge_expired(conn, LocalAudioSource(tmp_path)) == 1
    assert _status(conn, key) == "expired"
