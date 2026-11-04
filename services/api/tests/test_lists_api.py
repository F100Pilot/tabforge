import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

pytestmark = pytest.mark.db

SCORE = {
    "schema_version": 2,
    "tempo_bpm": 100,
    "time_signature": [4, 4],
    "tuning": [64, 59, 55, 50, 45, 40],
    "bars": [{"beats": [{"duration": 1, "notes": [{"string": 6, "fret": 3}]}]}],
}


def _user(conn, email: str):  # type: ignore[no-untyped-def]
    return conn.execute(
        text(
            "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
            "DO UPDATE SET email = EXCLUDED.email RETURNING id"
        ),
        {"e": email},
    ).scalar_one()


def _job(engine: Engine, email: str, status: str, title: str | None, age_min: int) -> None:
    with engine.begin() as conn:
        user = _user(conn, email)
        audio = conn.execute(
            text(
                "INSERT INTO audio_assets (user_id, status, source_kind, content_type, size_bytes,"
                " storage_key, duration_ms) VALUES (:u, 'uploaded', 'mix', 'audio/wav', 10,"
                " gen_random_uuid()::text, 192000) RETURNING id"
            ),
            {"u": user},
        ).scalar_one()
        tab = None
        if title:
            tab = conn.execute(
                text("INSERT INTO tabs (owner_id, title) VALUES (:u, :t) RETURNING id"),
                {"u": user, "t": title},
            ).scalar_one()
            rev = conn.execute(
                text(
                    "INSERT INTO tab_revisions (tab_id, score, source) "
                    "VALUES (:t, CAST(:s AS jsonb), 'ai') RETURNING id"
                ),
                {"t": tab, "s": json.dumps(SCORE)},
            ).scalar_one()
            conn.execute(
                text("UPDATE tabs SET current_revision_id = :r WHERE id = :t"),
                {"r": rev, "t": tab},
            )
        conn.execute(
            text(
                "INSERT INTO jobs (audio_id, status, tab_id, created_at) "
                "VALUES (:a, :s, :t, now() - make_interval(mins => :m))"
            ),
            {"a": audio, "s": status, "t": tab, "m": age_min},
        )


def test_list_jobs_newest_first_with_tab_title_and_duration(
    client: TestClient, engine: Engine
) -> None:
    _job(engine, "dev@tabforge.local", "done", "Riff", age_min=60)
    _job(engine, "dev@tabforge.local", "running", None, age_min=5)
    _job(engine, "other@example.com", "done", "Not mine", age_min=1)

    resp = client.get("/v1/jobs")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [(i["status"], i["tab_title"]) for i in items] == [("running", None), ("done", "Riff")]
    assert items[0]["duration_ms"] == 192000


def test_list_jobs_limit(client: TestClient, engine: Engine) -> None:
    for minutes in range(3):
        _job(engine, "dev@tabforge.local", "queued", None, age_min=minutes)
    assert len(client.get("/v1/jobs?limit=2").json()["items"]) == 2
    assert client.get("/v1/jobs?limit=0").status_code == 422
    assert client.get("/v1/jobs?limit=101").status_code == 422


def test_list_tabs_only_own(client: TestClient, engine: Engine) -> None:
    _job(engine, "dev@tabforge.local", "done", "Mine", age_min=10)
    _job(engine, "other@example.com", "done", "Theirs", age_min=1)
    items = client.get("/v1/tabs").json()["items"]
    assert [i["title"] for i in items] == ["Mine"]
    assert set(items[0]) == {"id", "title", "tuning", "visibility", "created_at"}
