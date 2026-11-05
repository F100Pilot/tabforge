"""ADR-0011 over HTTP: the learning profile, and the writes that mark it for a refresh."""

import hashlib
import json
import uuid
from typing import Any

import pytest
from conftest import FakeMailer, FakeStore, _settings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from test_reference_api import _apply, _body, _moved, _notes, _rev, _score, _tab, _tab_for

from tabforge_api.auth import SESSION_COOKIE
from tabforge_api.main import create_app
from tabforge_api.routes.tuning import mark_stale

pytestmark = pytest.mark.db

DEV = "dev@tabforge.local"
WEIGHTS = {"span": 1.0, "height": -0.05, "move": 0.25, "open_move": 0.1}


def _user_id(engine: Engine, email: str = DEV) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).scalar_one()
        )


def _profile(engine: Engine, email: str = DEV) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT p.* FROM fretting_profiles p JOIN users u ON u.id = p.user_id "
                    "WHERE u.email = :e"
                ),
                {"e": email},
            )
            .mappings()
            .one_or_none()
        )
    return None if row is None else dict(row)


def _set_profile(engine: Engine, user_id: str, **values: Any) -> None:
    row = {
        "status": "ready",
        "weights": None,
        "default_accuracy": None,
        "tuned_accuracy": None,
        "tabs": 0,
        "notes": 0,
        **values,
    }
    row["weights"] = None if row["weights"] is None else json.dumps(row["weights"])
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO fretting_profiles (user_id, status, weights, default_accuracy, "
                "tuned_accuracy, tabs, notes, requested_at, updated_at) VALUES (:u, :status, "
                "CAST(:weights AS jsonb), :default_accuracy, :tuned_accuracy, :tabs, :notes, "
                "now() - interval '1 hour', now() - interval '1 minute') "
                "ON CONFLICT (user_id) DO UPDATE SET status = EXCLUDED.status, "
                "weights = EXCLUDED.weights, default_accuracy = EXCLUDED.default_accuracy, "
                "tuned_accuracy = EXCLUDED.tuned_accuracy, tabs = EXCLUDED.tabs, "
                "notes = EXCLUDED.notes, requested_at = EXCLUDED.requested_at, "
                "updated_at = EXCLUDED.updated_at"
            ),
            {"u": user_id, **row},
        )


def test_without_a_profile_the_status_is_none(client: TestClient) -> None:
    resp = client.get("/v1/me/tuning")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "none",
        "tabs": 0,
        "notes": 0,
        "default_accuracy": None,
        "tuned_accuracy": None,
        "in_use": False,
        "weights": None,
        "updated_at": None,
        "min_notes": 200,
        "min_tabs": 2,
    }


def test_refresh_now_marks_the_profile_stale(client: TestClient, engine: Engine) -> None:
    resp = client.post("/v1/me/tuning")
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "stale"
    assert resp.json()["in_use"] is False
    profile = _profile(engine)
    assert profile is not None
    assert profile["status"] == "stale"
    assert profile["requested_at"] is not None
    assert client.get("/v1/me/tuning").json()["status"] == "stale"


def test_ready_profile_with_weights_is_in_use(client: TestClient, engine: Engine) -> None:
    _tab(engine)  # creates the dev user
    _set_profile(
        engine,
        _user_id(engine),
        weights=WEIGHTS,
        default_accuracy=0.612345,
        tuned_accuracy=0.71,
        tabs=3,
        notes=900,
    )
    body = client.get("/v1/me/tuning").json()
    assert body["status"] == "ready"
    assert body["in_use"] is True
    assert body["weights"] == WEIGHTS
    assert (body["tabs"], body["notes"]) == (3, 900)
    assert (body["default_accuracy"], body["tuned_accuracy"]) == (0.6123, 0.71)
    assert body["updated_at"] is not None


@pytest.mark.parametrize(
    ("status", "weights"),
    [("ready", None), ("insufficient", None), ("stale", WEIGHTS)],
)
def test_profile_is_in_use_only_when_ready_with_weights(
    client: TestClient, engine: Engine, status: str, weights: dict[str, float] | None
) -> None:
    _tab(engine)
    _set_profile(engine, _user_id(engine), status=status, weights=weights)
    body = client.get("/v1/me/tuning").json()
    assert body["status"] == status
    assert body["in_use"] is False
    assert body["weights"] == weights


def test_marking_again_keeps_the_last_result(client: TestClient, engine: Engine) -> None:
    _tab(engine)
    user = _user_id(engine)
    _set_profile(engine, user, weights=WEIGHTS, tabs=3, notes=900)
    before = _profile(engine)
    assert before is not None
    body = client.post("/v1/me/tuning").json()
    assert (body["status"], body["tabs"], body["notes"], body["weights"]) == (
        "stale",
        3,
        900,
        WEIGHTS,
    )
    after = _profile(engine)
    assert after is not None
    assert after["requested_at"] > before["requested_at"]


def test_saving_a_reference_marks_the_profile_stale(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    assert _profile(engine) is None
    assert client.put(f"/v1/tabs/{tab}/reference", json=_body()).status_code == 200
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "stale"


def test_deleting_a_reference_marks_the_profile_stale(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    _set_profile(engine, _user_id(engine))
    assert client.delete(f"/v1/tabs/{tab}/reference").status_code == 204
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "stale"
    _set_profile(engine, _user_id(engine))
    assert client.delete(f"/v1/tabs/{tab}/reference").status_code == 204  # nothing to delete
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "ready"


def test_applying_corrections_marks_the_profile_stale(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body(_moved(_notes())))
    _set_profile(engine, _user_id(engine))
    resp = _apply(client, tab, _rev(client, tab))
    assert resp.status_code == 201
    assert resp.json()["applied"] > 0
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "stale"


def test_applying_nothing_leaves_the_profile_alone(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    _set_profile(engine, _user_id(engine))
    resp = _apply(client, tab, _rev(client, tab))
    assert resp.status_code == 200
    assert resp.json()["applied"] == 0
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "ready"


def test_saving_a_revision_marks_the_profile_stale(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    _set_profile(engine, _user_id(engine))
    score = _score()
    score["bars"][0]["beats"][0]["notes"][0]["fret"] = 9
    resp = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": _rev(client, tab), "score": score}
    )
    assert resp.status_code == 201, resp.text
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "stale"


def test_marking_never_fails_the_request(engine: Engine) -> None:
    """A lock timeout (or any database error) in the savepoint is swallowed; the rest commits."""
    tab = _tab(engine)
    user = _user_id(engine)
    _set_profile(engine, user)
    with engine.connect() as locker, Session(engine) as session:
        locker.execute(
            text("SELECT 1 FROM fretting_profiles WHERE user_id = :u FOR UPDATE"), {"u": user}
        )
        session.execute(text("SET LOCAL lock_timeout = '50ms'"))
        mark_stale(session, uuid.UUID(user))  # would block forever without the timeout
        session.execute(text("UPDATE tabs SET title = 'kept' WHERE id = :t"), {"t": tab})
        session.commit()
        locker.rollback()
    profile = _profile(engine)
    assert profile is not None and profile["status"] == "ready"  # the upsert did fail
    with engine.connect() as conn:
        title = conn.execute(text("SELECT title FROM tabs WHERE id = :t"), {"t": tab})
        assert title.scalar_one() == "kept"


def test_profile_is_deleted_with_the_account(client: TestClient, engine: Engine) -> None:
    client.post("/v1/me/tuning")
    assert _profile(engine) is not None
    assert client.delete("/v1/me").status_code == 204
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fretting_profiles")).scalar_one() == 0


def test_refresh_needs_csrf_with_cookie_auth(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    settings = _settings(database_url, dev_auth=False, session_cookie_secure=False)
    auth = TestClient(create_app(settings, store=store, mailer=mailer))
    with engine.begin() as conn:
        user = conn.execute(
            text("INSERT INTO users (email) VALUES ('tuning@example.com') RETURNING id")
        ).scalar_one()
        _tab_for(conn, str(user))
        conn.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at) "
                "VALUES (:u, :h, 'csrf-secret', now() + interval '1 day')"
            ),
            {"u": user, "h": hashlib.sha256(b"cookie").hexdigest()},
        )
    auth.cookies.set(SESSION_COOKIE, "cookie")
    assert auth.post("/v1/me/tuning").status_code == 403
    assert _profile(engine, "tuning@example.com") is None
    assert auth.get("/v1/me/tuning").status_code == 200  # reads need no token
    resp = auth.post("/v1/me/tuning", headers={"X-CSRF-Token": "csrf-secret"})
    assert resp.status_code == 202
    assert auth.get("/v1/me/tuning").json()["status"] == "stale"


def test_refresh_is_rate_limited(engine: Engine, database_url: str, store: FakeStore) -> None:
    app = create_app(_settings(database_url, write_rate_per_minute=2), store=store)
    limited = TestClient(app)
    assert [limited.post("/v1/me/tuning").status_code for _ in range(3)] == [202, 202, 429]
    app.state.engine.dispose()


def test_tuning_needs_authentication(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    settings = _settings(database_url, dev_auth=False)
    anonymous = TestClient(create_app(settings, store=store, mailer=mailer))
    assert anonymous.get("/v1/me/tuning").status_code == 401
    assert anonymous.post("/v1/me/tuning").status_code == 401
