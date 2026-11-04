"""ADR-0009 over HTTP against Postgres: reference tab (notes only) and comparison."""

import hashlib
import json
from typing import Any

import pytest
from conftest import FakeMailer, FakeStore, _settings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from tabforge_score import Score
from tabforge_score.compare import score_events

from tabforge_api.auth import SESSION_COOKIE
from tabforge_api.main import create_app

pytestmark = pytest.mark.db

BARS = 3
PITCHES = (1, 2, 3, 4)  # frets on string 6 (low E), one per quarter


def _score() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tuning": [64, 59, 55, 50, 45, 40],
        "bars": [
            {
                "beats": [
                    {"duration": 4, "notes": [{"string": 6, "fret": fret + bar}]}
                    for fret in PITCHES
                ]
            }
            for bar in range(BARS)
        ],
    }


def _notes(shift: float = 0.0) -> list[dict[str, Any]]:
    events = score_events(Score.model_validate(_score()))
    return [
        {
            "onset": float(e.onset) + shift,
            "pitch": e.pitch,
            "string": e.string,
            "fret": e.fret,
            "bar": e.bar,
        }
        for e in events
    ]


def _body(notes: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "filename": "song.gp5",
        "track": "Lead guitar",
        "notes": _notes() if notes is None else notes,
    }
    body.update(overrides)
    return body


def _tab(engine: Engine, email: str = "dev@tabforge.local") -> str:
    with engine.begin() as conn:
        user = conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
                "DO UPDATE SET email = EXCLUDED.email RETURNING id"
            ),
            {"e": email},
        ).scalar_one()
        return _tab_for(conn, str(user))


def _tab_for(conn: Any, user_id: str) -> str:
    tab = conn.execute(
        text("INSERT INTO tabs (owner_id, title) VALUES (:u, 'T') RETURNING id"), {"u": user_id}
    ).scalar_one()
    rev = conn.execute(
        text(
            "INSERT INTO tab_revisions (tab_id, score, source) "
            "VALUES (:t, CAST(:s AS jsonb), 'ai') RETURNING id"
        ),
        {"t": tab, "s": json.dumps(_score())},
    ).scalar_one()
    conn.execute(
        text("UPDATE tabs SET current_revision_id = :r WHERE id = :t"), {"r": rev, "t": tab}
    )
    return str(tab)


def test_put_get_summary(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.put(f"/v1/tabs/{tab}/reference", json=_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "song.gp5"
    assert body["track"] == "Lead guitar"
    assert body["notes"] == BARS * len(PITCHES)
    assert client.get(f"/v1/tabs/{tab}/reference").json() == body


def test_get_without_reference_is_404(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.get(f"/v1/tabs/{tab}/reference")
    assert resp.status_code == 404
    assert resp.json()["code"] == "reference_not_found"


def test_comparison_of_identical_tab_is_perfect(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    resp = client.get(f"/v1/tabs/{tab}/comparison")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    current = client.get(f"/v1/tabs/{tab}").json()["revision"]["id"]
    assert body["revision_id"] == current
    assert body["shift_quarters"] == 0
    assert body["scale"] == 1
    assert body["matched"] == body["ai_notes"] == body["reference_notes"] == 12
    assert body["recall"] == body["precision"] == body["f1"] == 1
    assert body["position_accuracy"] == 1
    assert body["onset_error"] == 0
    assert body["bars"] == [
        {"bar": b, "reference_notes": 4, "matched": 4, "positions_ok": 4} for b in (1, 2, 3)
    ]


def test_comparison_finds_the_shift(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body(_notes(shift=8.0)))
    body = client.get(f"/v1/tabs/{tab}/comparison").json()
    assert body["shift_quarters"] == 8
    assert body["recall"] == 1


def test_comparison_without_reference_is_404(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.get(f"/v1/tabs/{tab}/comparison")
    assert resp.status_code == 404
    assert resp.json()["code"] == "reference_not_found"


def test_comparison_without_notes_in_common_has_null_accuracy(
    client: TestClient, engine: Engine
) -> None:
    tab = _tab(engine)
    other = [{"onset": 0.0, "pitch": 100, "string": 1, "fret": 0, "bar": 1}]
    client.put(f"/v1/tabs/{tab}/reference", json=_body(other))
    body = client.get(f"/v1/tabs/{tab}/comparison").json()
    assert body["matched"] == 0
    assert body["position_accuracy"] is None
    assert body["onset_error"] is None


def test_put_replaces_existing_reference(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    one = [{"onset": 0.0, "pitch": 40, "string": 6, "fret": 0, "bar": 1}]
    resp = client.put(f"/v1/tabs/{tab}/reference", json=_body(one, filename="b.gp7", track=""))
    assert resp.status_code == 200
    assert resp.json()["notes"] == 1
    assert client.get(f"/v1/tabs/{tab}/reference").json()["filename"] == "b.gp7"
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM tab_references")).scalar_one()
    assert count == 1


def test_delete_is_idempotent(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    assert client.delete(f"/v1/tabs/{tab}/reference").status_code == 204
    assert client.get(f"/v1/tabs/{tab}/reference").status_code == 404
    assert client.delete(f"/v1/tabs/{tab}/reference").status_code == 204


def test_other_users_tab_is_404_on_every_route(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, "other@example.com")
    assert client.put(f"/v1/tabs/{tab}/reference", json=_body()).status_code == 404
    assert client.get(f"/v1/tabs/{tab}/reference").status_code == 404
    assert client.delete(f"/v1/tabs/{tab}/reference").status_code == 404
    assert client.get(f"/v1/tabs/{tab}/comparison").status_code == 404


def test_other_users_reference_is_untouched(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, "other@example.com")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tab_references (tab_id, filename, track, notes) "
                "VALUES (:t, 'x.gp5', '', '[]')"
            ),
            {"t": tab},
        )
    client.delete(f"/v1/tabs/{tab}/reference")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tab_references")).scalar_one() == 1


def _note(**overrides: Any) -> dict[str, Any]:
    note: dict[str, Any] = {"onset": 0.0, "pitch": 40, "string": 6, "fret": 0, "bar": 1}
    note.update(overrides)
    return note


@pytest.mark.parametrize(
    "body",
    [
        _body([_note(string=7)]),
        _body([_note(string=0)]),
        _body([_note(fret=31)]),
        _body([_note(pitch=128)]),
        _body([_note(bar=0)]),
        _body([_note(bar=10001)]),
        _body([_note(onset=-1.0)]),
        _body([_note(onset=100001.0)]),
        _body([]),
        _body(filename=""),
        _body(filename="x" * 201),
        _body(track="x" * 201),
        {"filename": "a", "track": ""},
    ],
)
def test_invalid_bodies_are_422(client: TestClient, engine: Engine, body: dict[str, Any]) -> None:
    tab = _tab(engine)
    assert client.put(f"/v1/tabs/{tab}/reference", json=body).status_code == 422


def test_more_than_20000_notes_is_422(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.put(f"/v1/tabs/{tab}/reference", json=_body([_note()] * 20_001))
    assert resp.status_code == 422


def test_20000_notes_are_accepted(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.put(f"/v1/tabs/{tab}/reference", json=_body([_note()] * 20_000))
    assert resp.status_code == 200
    assert resp.json()["notes"] == 20_000


def test_body_over_2_mb_is_413(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    huge = json.dumps(_body(filename="x" * 2_100_000))
    resp = client.put(
        f"/v1/tabs/{tab}/reference", content=huge, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "payload_too_large"


def test_reference_is_removed_with_its_tab(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    with engine.begin() as conn:
        conn.execute(text("UPDATE tabs SET current_revision_id = NULL WHERE id = :t"), {"t": tab})
        conn.execute(text("DELETE FROM tab_revisions WHERE tab_id = :t"), {"t": tab})
        conn.execute(text("DELETE FROM tabs WHERE id = :t"), {"t": tab})
        assert conn.execute(text("SELECT count(*) FROM tab_references")).scalar_one() == 0


def test_account_deletion_removes_references(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    assert client.delete("/v1/me").status_code == 204
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tab_references")).scalar_one() == 0


def test_writes_need_csrf_with_cookie_auth(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    settings = _settings(database_url, dev_auth=False, session_cookie_secure=False)
    auth = TestClient(create_app(settings, store=store, mailer=mailer))
    with engine.begin() as conn:
        user = conn.execute(
            text("INSERT INTO users (email) VALUES ('csrf@example.com') RETURNING id")
        ).scalar_one()
        tab = _tab_for(conn, str(user))
        conn.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at) "
                "VALUES (:u, :h, 'csrf-secret', now() + interval '1 day')"
            ),
            {"u": user, "h": hashlib.sha256(b"cookie").hexdigest()},
        )
    auth.cookies.set(SESSION_COOKIE, "cookie")
    url = f"/v1/tabs/{tab}/reference"
    assert auth.put(url, json=_body()).status_code == 403
    assert auth.delete(url).status_code == 403
    headers = {"X-CSRF-Token": "csrf-secret"}
    assert auth.put(url, json=_body(), headers=headers).status_code == 200
    assert auth.get(url).status_code == 200  # reads need no token
    assert auth.delete(url, headers=headers).status_code == 204
