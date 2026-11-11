"""POST /v1/tabs/{id}/refret (ADR-0016): the tab placed again with the learned weights."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from tabforge_score import Score
from tabforge_score.compare import score_events

pytestmark = pytest.mark.db

ME = "dev@tabforge.local"
STANDARD = [64, 59, 55, 50, 45, 40]
# Prefers low frets strongly: moves the riff below from fret 7+ on string 4 to first position.
LOW = {"span": 1.0, "height": 0.4, "move": 0.1, "open_move": 0.0}


def _score() -> dict[str, Any]:
    frets = [7, 9, 11, 12]  # A B C# D on the D string, high up
    return {
        "schema_version": 2,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tuning": STANDARD,
        "bars": [{"beats": [{"duration": 4, "notes": [{"string": 4, "fret": f}]} for f in frets]}],
    }


def _user(conn: Any, email: str) -> Any:
    return conn.execute(
        text(
            "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
            "DO UPDATE SET email = EXCLUDED.email RETURNING id"
        ),
        {"e": email},
    ).scalar_one()


def _tab(engine: Engine, email: str = ME) -> tuple[str, str]:
    with engine.begin() as conn:
        user = _user(conn, email)
        tab = conn.execute(
            text("INSERT INTO tabs (owner_id, title) VALUES (:u, 'Riff') RETURNING id"),
            {"u": user},
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
    return str(tab), str(rev)


def _profile(
    engine: Engine, status: str = "ready", weights: dict[str, float] | None = LOW, email: str = ME
) -> None:
    with engine.begin() as conn:
        user = _user(conn, email)
        conn.execute(
            text(
                "INSERT INTO fretting_profiles (user_id, status, weights, tabs, notes) "
                "VALUES (:u, :s, CAST(:w AS jsonb), 1, 300)"
            ),
            {"u": user, "s": status, "w": None if weights is None else json.dumps(weights)},
        )


def test_refret_saves_a_learned_revision(client: TestClient, engine: Engine) -> None:
    tab, rev = _tab(engine)
    _profile(engine)
    resp = client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["changed"] == 4
    assert body["tab"]["revision"]["source"] == "learned"
    assert body["tab"]["revision"]["id"] != rev
    new = Score.model_validate(body["tab"]["revision"]["score"])
    old = Score.model_validate(_score())
    assert [e.pitch for e in score_events(new)] == [e.pitch for e in score_events(old)]
    assert all(e.fret < 7 for e in score_events(new))
    assert client.get(f"/v1/tabs/{tab}").json()["revision"]["id"] == body["tab"]["revision"]["id"]
    with engine.connect() as conn:  # the learning reads only user revisions: nothing to refresh
        status = conn.execute(text("SELECT status FROM fretting_profiles")).scalar_one()
    assert status == "ready"


def test_nothing_to_change_creates_no_revision(client: TestClient, engine: Engine) -> None:
    tab, rev = _tab(engine)
    _profile(engine)
    first = client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev}).json()
    again = client.post(
        f"/v1/tabs/{tab}/refret", json={"base_revision_id": first["tab"]["revision"]["id"]}
    )
    assert again.status_code == 200
    assert again.json()["changed"] == 0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tab_revisions")).scalar_one() == 2


@pytest.mark.parametrize(
    ("status", "weights"), [("ready", None), ("insufficient", None), ("stale", LOW)]
)
def test_needs_learned_weights_in_use(
    client: TestClient, engine: Engine, status: str, weights: dict[str, float] | None
) -> None:
    tab, rev = _tab(engine)
    _profile(engine, status, weights)
    resp = client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev})
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_learned_weights"


def test_without_a_profile(client: TestClient, engine: Engine) -> None:
    tab, rev = _tab(engine)
    resp = client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev})
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_learned_weights"


def test_stale_base_revision_is_a_conflict(client: TestClient, engine: Engine) -> None:
    tab, _ = _tab(engine)
    _profile(engine)
    resp = client.post(
        f"/v1/tabs/{tab}/refret", json={"base_revision_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "revision_conflict"


def test_only_the_owner(client: TestClient, engine: Engine) -> None:
    tab, rev = _tab(engine, email="other@example.com")
    _profile(engine)
    resp = client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev})
    assert resp.status_code == 404


def test_revision_list_shows_the_learned_source(client: TestClient, engine: Engine) -> None:
    tab, rev = _tab(engine)
    _profile(engine)
    client.post(f"/v1/tabs/{tab}/refret", json={"base_revision_id": rev})
    items = client.get(f"/v1/tabs/{tab}/revisions").json()["items"]
    assert [i["source"] for i in items][:2] in (["learned", "ai"], ["ai", "learned"])
