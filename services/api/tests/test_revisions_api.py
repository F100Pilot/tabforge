import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

pytestmark = pytest.mark.db


def _score(fret: int = 3) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tuning": [64, 59, 55, 50, 45, 40],
        "bars": [{"beats": [{"duration": 1, "notes": [{"string": 6, "fret": fret}]}]}],
    }


def _tab(engine: Engine, email: str = "dev@tabforge.local") -> tuple[str, str]:
    with engine.begin() as conn:
        user = conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
                "DO UPDATE SET email = EXCLUDED.email RETURNING id"
            ),
            {"e": email},
        ).scalar_one()
        tab = conn.execute(
            text("INSERT INTO tabs (owner_id, title) VALUES (:u, 'T') RETURNING id"), {"u": user}
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


def test_save_revision_creates_user_revision_and_makes_it_current(
    client: TestClient, engine: Engine
) -> None:
    tab, base = _tab(engine)
    resp = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score(5)}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["revision"]["source"] == "user"
    assert body["revision"]["id"] != base
    assert body["alphatex"].endswith("5.6.1 |")
    current = client.get(f"/v1/tabs/{tab}").json()
    assert current["revision"]["id"] == body["revision"]["id"]


def test_previous_revisions_are_kept_unchanged(client: TestClient, engine: Engine) -> None:
    tab, base = _tab(engine)
    client.post(f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score(5)})
    history = client.get(f"/v1/tabs/{tab}/revisions").json()["items"]
    assert [h["source"] for h in history] == ["user", "ai"]
    old = client.get(f"/v1/tabs/{tab}/revisions/{base}").json()
    assert old["score"]["bars"][0]["beats"][0]["notes"][0]["fret"] == 3


def test_stale_base_revision_is_409(client: TestClient, engine: Engine) -> None:
    tab, base = _tab(engine)
    first = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score(5)}
    )
    assert first.status_code == 201
    stale = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score(7)}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"


def test_invalid_score_is_422(client: TestClient, engine: Engine) -> None:
    tab, base = _tab(engine)
    bad = _score()
    bad["bars"][0]["beats"][0]["duration"] = 2  # bar no longer fills 4/4
    resp = client.post(f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": bad})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_other_users_tab_is_404(client: TestClient, engine: Engine) -> None:
    tab, base = _tab(engine, "other@example.com")
    resp = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score()}
    )
    assert resp.status_code == 404
    assert client.get(f"/v1/tabs/{tab}/revisions").status_code == 404
    assert client.get(f"/v1/tabs/{tab}/revisions/{base}").status_code == 404


def test_revision_of_another_tab_is_404(client: TestClient, engine: Engine) -> None:
    tab_a, _ = _tab(engine)
    _, rev_b = _tab(engine)
    assert client.get(f"/v1/tabs/{tab_a}/revisions/{rev_b}").status_code == 404


def test_oversized_body_is_413(client: TestClient, engine: Engine) -> None:
    tab, base = _tab(engine)
    payload = json.dumps({"base_revision_id": base, "score": _score(), "pad": "x" * 1_100_000})
    resp = client.post(
        f"/v1/tabs/{tab}/revisions", content=payload, headers={"content-type": "application/json"}
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "payload_too_large"
