"""Deleting a song: DELETE /v1/jobs/{id} and /v1/tabs/{id} remove the audio, job and tab."""

import json
import uuid

import pytest
from conftest import FakeStore, _settings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tabforge_api.main import create_app

pytestmark = pytest.mark.db

ME = "dev@tabforge.local"
SCORE = {
    "schema_version": 2,
    "tempo_bpm": 100,
    "time_signature": [4, 4],
    "tuning": [64, 59, 55, 50, 45, 40],
    "bars": [{"beats": [{"duration": 1, "notes": [{"string": 6, "fret": 3}]}]}],
}


def _song(
    engine: Engine, store: FakeStore, email: str = ME, status: str = "done", tab: bool = True
) -> dict[str, str | None]:
    """One upload: audio object + asset + job, and the tab the job produced."""
    key = f"audio/{uuid.uuid4()}"
    store.put(key, b"RIFF....WAVE", "audio/wav")
    with engine.begin() as conn:
        user = conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
                "DO UPDATE SET email = EXCLUDED.email RETURNING id"
            ),
            {"e": email},
        ).scalar_one()
        audio = conn.execute(
            text(
                "INSERT INTO audio_assets (user_id, status, source_kind, content_type, size_bytes,"
                " storage_key) VALUES (:u, 'uploaded', 'mix', 'audio/wav', 12, :k) RETURNING id"
            ),
            {"u": user, "k": key},
        ).scalar_one()
        tab_id = None
        if tab:
            tab_id = conn.execute(
                text("INSERT INTO tabs (owner_id, title) VALUES (:u, 'Riff') RETURNING id"),
                {"u": user},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO tab_revisions (tab_id, score, source) "
                    "VALUES (:t, CAST(:s AS jsonb), 'ai')"
                ),
                {"t": tab_id, "s": json.dumps(SCORE)},
            )
        job = conn.execute(
            text("INSERT INTO jobs (audio_id, status, tab_id) VALUES (:a, :s, :t) RETURNING id"),
            {"a": audio, "s": status, "t": tab_id},
        ).scalar_one()
    return {"key": key, "job": str(job), "tab": None if tab_id is None else str(tab_id)}


TABLES = ("audio_assets", "jobs", "tabs", "tab_revisions", "tab_references")


def _count(engine: Engine, table: str) -> int:
    assert table in TABLES  # a fixed table name, never user input
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608


def _gone(engine: Engine, store: FakeStore, song: dict[str, str | None]) -> bool:
    return song["key"] not in store.objects and all(
        _count(engine, t) == 0 for t in ("audio_assets", "jobs", "tabs", "tab_revisions")
    )


def test_deleting_a_job_removes_its_audio_job_and_tab(
    client: TestClient, engine: Engine, store: FakeStore
) -> None:
    song = _song(engine, store)
    assert client.delete(f"/v1/jobs/{song['job']}").status_code == 204
    assert _gone(engine, store, song)
    assert client.get(f"/v1/jobs/{song['job']}").status_code == 404


def test_deleting_a_failed_job_without_a_tab(
    client: TestClient, engine: Engine, store: FakeStore
) -> None:
    song = _song(engine, store, status="failed", tab=False)
    assert client.delete(f"/v1/jobs/{song['job']}").status_code == 204
    assert _gone(engine, store, song)


def test_deleting_a_tab_removes_the_job_and_audio_behind_it(
    client: TestClient, engine: Engine, store: FakeStore
) -> None:
    song = _song(engine, store)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tab_references (tab_id, filename, track, notes) "
                "VALUES (:t, 'song.gp', 'Guitar', '[]'::jsonb)"
            ),
            {"t": song["tab"]},
        )
    assert client.delete(f"/v1/tabs/{song['tab']}").status_code == 204
    assert _gone(engine, store, song)
    assert _count(engine, "tab_references") == 0
    with engine.connect() as conn:  # less training data (ADR-0011): the profile is refreshed
        status = conn.execute(text("SELECT status FROM fretting_profiles")).scalar_one()
    assert status == "stale"


def test_a_running_job_cannot_be_deleted(
    client: TestClient, engine: Engine, store: FakeStore
) -> None:
    song = _song(engine, store, status="running", tab=False)
    resp = client.delete(f"/v1/jobs/{song['job']}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "job_running"
    assert song["key"] in store.objects
    assert _count(engine, "jobs") == 1


def test_other_users_songs_are_not_found(
    client: TestClient, engine: Engine, store: FakeStore
) -> None:
    theirs = _song(engine, store, email="other@example.com")
    assert client.delete(f"/v1/jobs/{theirs['job']}").status_code == 404
    assert client.delete(f"/v1/tabs/{theirs['tab']}").status_code == 404
    assert theirs["key"] in store.objects
    assert _count(engine, "tabs") == 1
    assert client.delete(f"/v1/jobs/{uuid.uuid4()}").status_code == 404


class BrokenStore(FakeStore):
    def delete(self, key: str) -> None:
        raise OSError("s3 down")


def test_a_storage_failure_deletes_nothing(engine: Engine, database_url: str) -> None:
    store = BrokenStore()
    client = TestClient(create_app(_settings(database_url), store=store))
    song = _song(engine, store)
    resp = client.delete(f"/v1/jobs/{song['job']}")
    assert resp.status_code == 503
    assert resp.json()["code"] == "storage_unavailable"
    assert _count(engine, "jobs") == 1 and _count(engine, "tabs") == 1
