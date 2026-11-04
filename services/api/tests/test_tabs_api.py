import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

pytestmark = pytest.mark.db

SCORE = {
    "schema_version": 1,
    "tempo_bpm": 100,
    "time_signature": [4, 4],
    "tuning": [64, 59, 55, 50, 45, 40],
    "bars": [{"beats": [{"duration": 1, "notes": [{"string": 6, "fret": 3}]}]}],
}


def _insert_tab(engine: Engine, email: str, title: str, score: object) -> str:
    with engine.begin() as conn:
        user = conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
                "DO UPDATE SET email = EXCLUDED.email RETURNING id"
            ),
            {"e": email},
        ).scalar_one()
        tab = conn.execute(
            text("INSERT INTO tabs (owner_id, title) VALUES (:u, :t) RETURNING id"),
            {"u": user, "t": title},
        ).scalar_one()
        rev = conn.execute(
            text(
                "INSERT INTO tab_revisions (tab_id, score, source) "
                "VALUES (:t, CAST(:s AS jsonb), 'ai') RETURNING id"
            ),
            {"t": tab, "s": json.dumps(score)},
        ).scalar_one()
        conn.execute(
            text("UPDATE tabs SET current_revision_id = :r WHERE id = :t"), {"r": rev, "t": tab}
        )
    return str(tab)


def test_get_tab_returns_score_and_alphatex(client: TestClient, engine: Engine) -> None:
    tab_id = _insert_tab(engine, "dev@tabforge.local", 'Riff "1"', SCORE)
    resp = client.get(f"/v1/tabs/{tab_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["visibility"] == "private"
    assert body["revision"]["source"] == "ai"
    assert body["revision"]["score"] == SCORE
    assert body["alphatex"].startswith('\\title "Riff \\"1\\"" \\tempo 100 ')
    assert body["alphatex"].endswith("3.6.1 |")


def test_other_users_tab_is_not_found(client: TestClient, engine: Engine) -> None:
    tab_id = _insert_tab(engine, "other@example.com", "Theirs", SCORE)
    assert client.get(f"/v1/tabs/{tab_id}").status_code == 404
