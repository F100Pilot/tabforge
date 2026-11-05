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


def _v3_score() -> dict[str, Any]:
    """Lead = the v2 riff on string 6; Rhythm = other notes, on string 4."""
    lead = {k: _score()[k] for k in ("tuning", "bars")}
    rhythm = {
        "tuning": lead["tuning"],
        "bars": [
            {"beats": [{"duration": 2, "notes": [{"string": 4, "fret": 7 + bar}]}] * 2}
            for bar in range(BARS)
        ],
    }
    return {
        "schema_version": 3,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tracks": [{"name": "Lead", **lead}, {"name": "Rhythm", **rhythm}],
    }


def _track_notes(track: int) -> list[dict[str, Any]]:
    events = score_events(Score.model_validate(_v3_score()), track=track)
    return [
        {
            "onset": float(e.onset),
            "pitch": e.pitch,
            "string": e.string,
            "fret": e.fret,
            "bar": e.bar,
        }
        for e in events
    ]


def _tab(
    engine: Engine, email: str = "dev@tabforge.local", score: dict[str, Any] | None = None
) -> str:
    with engine.begin() as conn:
        user = conn.execute(
            text(
                "INSERT INTO users (email) VALUES (:e) ON CONFLICT ((lower(email))) "
                "DO UPDATE SET email = EXCLUDED.email RETURNING id"
            ),
            {"e": email},
        ).scalar_one()
        return _tab_for(conn, str(user), score)


def _tab_for(conn: Any, user_id: str, score: dict[str, Any] | None = None) -> str:
    tab = conn.execute(
        text("INSERT INTO tabs (owner_id, title) VALUES (:u, 'T') RETURNING id"), {"u": user_id}
    ).scalar_one()
    rev = conn.execute(
        text(
            "INSERT INTO tab_revisions (tab_id, score, source) "
            "VALUES (:t, CAST(:s AS jsonb), 'ai') RETURNING id"
        ),
        {"t": tab, "s": json.dumps(_score() if score is None else score)},
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


# Per track (ADR-0010) --------------------------------------------------------------------------


def test_references_of_tracks_0_and_1_are_independent(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, score=_v3_score())
    url = f"/v1/tabs/{tab}/reference"
    lead = client.put(url, json=_body(_track_notes(0), filename="lead.gp5"))
    assert lead.status_code == 200, lead.text
    rhythm = client.put(f"{url}?track=1", json=_body(_track_notes(1), filename="rhythm.gp5"))
    assert rhythm.status_code == 200, rhythm.text
    assert client.get(url).json()["filename"] == "lead.gp5"
    assert client.get(f"{url}?track=0").json()["filename"] == "lead.gp5"
    assert client.get(f"{url}?track=1").json()["filename"] == "rhythm.gp5"
    # Replacing one track's reference leaves the other alone.
    client.put(f"{url}?track=1", json=_body(_track_notes(1), filename="rhythm2.gp5"))
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT track_index, filename FROM tab_references ORDER BY track_index")
        ).all()
    assert [tuple(r) for r in rows] == [(0, "lead.gp5"), (1, "rhythm2.gp5")]
    assert client.delete(f"{url}?track=1").status_code == 204
    assert client.get(f"{url}?track=1").status_code == 404
    assert client.get(url).json()["filename"] == "lead.gp5"


def test_comparison_of_track_1_compares_the_rhythm_track(
    client: TestClient, engine: Engine
) -> None:
    tab = _tab(engine, score=_v3_score())
    client.put(f"/v1/tabs/{tab}/reference?track=1", json=_body(_track_notes(1)))
    body = client.get(f"/v1/tabs/{tab}/comparison?track=1").json()
    assert body["ai_notes"] == body["reference_notes"] == body["matched"] == 2 * BARS
    assert body["recall"] == body["precision"] == 1
    # Track 0 has no reference of its own.
    resp = client.get(f"/v1/tabs/{tab}/comparison")
    assert resp.status_code == 404
    assert resp.json()["code"] == "reference_not_found"


def test_comparison_of_track_0_uses_the_lead_track(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, score=_v3_score())
    client.put(f"/v1/tabs/{tab}/reference?track=0", json=_body(_track_notes(1)))
    body = client.get(f"/v1/tabs/{tab}/comparison?track=0").json()
    assert body["ai_notes"] == BARS * len(PITCHES)  # the Lead notes
    assert body["matched"] == 0  # the Rhythm notes are not in the Lead track


@pytest.mark.parametrize(
    ("score", "track"), [(None, 1), (_v3_score(), 2), (_v3_score(), 9), (None, 2**31 - 1)]
)
def test_track_beyond_the_current_revision_is_422(
    client: TestClient, engine: Engine, score: dict[str, Any] | None, track: int
) -> None:
    tab = _tab(engine, score=score)
    put = client.put(f"/v1/tabs/{tab}/reference?track={track}", json=_body())
    assert put.status_code == 422
    assert put.json()["code"] == "invalid_track"
    comparison = client.get(f"/v1/tabs/{tab}/comparison?track={track}")
    assert comparison.status_code == 422
    assert comparison.json()["code"] == "invalid_track"
    # Reading or deleting just uses the index.
    assert client.get(f"/v1/tabs/{tab}/reference?track={track}").status_code == 404
    assert client.delete(f"/v1/tabs/{tab}/reference?track={track}").status_code == 204


@pytest.mark.parametrize("track", ["-1", "x", "1.5", str(2**31), str(10**20)])
def test_track_must_be_a_non_negative_integer(
    client: TestClient, engine: Engine, track: str
) -> None:
    tab = _tab(engine)
    url = f"/v1/tabs/{tab}/reference?track={track}"
    assert client.put(url, json=_body()).status_code == 422
    assert client.get(url).status_code == 422
    assert client.delete(url).status_code == 422
    assert client.get(f"/v1/tabs/{tab}/comparison?track={track}").status_code == 422


# Differences and position corrections (ADR-0009) -------------------------------------------------


def _moved(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reference plays frets 5 and up of string 6 as the same pitch on string 5."""
    return [{**n, "string": 5, "fret": n["fret"] - 5} if n["fret"] >= 5 else dict(n) for n in notes]


MOVED = 3  # notes of _score() on string 6 at fret 5 or more


def _rev(client: TestClient, tab: str) -> str:
    return str(client.get(f"/v1/tabs/{tab}").json()["revision"]["id"])


def test_comparison_without_differences_has_zero_counts(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    diffs = client.get(f"/v1/tabs/{tab}/comparison").json()["differences"]
    assert diffs == {
        "counts": {"position": 0, "missing": 0, "extra": 0, "timing": 0},
        "items": [],
        "truncated": False,
    }


def test_comparison_lists_the_differences_by_onset(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    notes = _moved(_notes())
    notes[1]["onset"] += 0.2  # timing (string 6 fret 2 stays)
    notes.pop(0)  # extra: the AI's first note is not in the reference
    notes.append(
        {"onset": 50.0, "pitch": 100, "string": 1, "fret": 0, "bar": 13}
    )  # missing: not in the AI
    client.put(f"/v1/tabs/{tab}/reference", json=_body(notes))
    diffs = client.get(f"/v1/tabs/{tab}/comparison").json()["differences"]
    assert diffs["counts"] == {"position": MOVED, "missing": 1, "extra": 1, "timing": 1}
    assert diffs["truncated"] is False
    items = diffs["items"]
    assert [i["onset"] for i in items] == sorted(i["onset"] for i in items)
    assert items[0]["kind"] == "extra" and items[0]["onset"] == 0
    assert items[0]["ref"] is None and items[0]["ai"] == {
        "string": 6,
        "fret": 1,
        "bar": 1,
        "beat": 0,
    }
    assert items[-1]["kind"] == "missing" and items[-1]["ai"] is None
    assert items[-1]["ref"] == {"string": 1, "fret": 0}
    timing = next(i for i in items if i["kind"] == "timing")
    assert timing["onset_error"] == pytest.approx(0.2)
    assert timing["ai"] == {"string": 6, "fret": 2, "bar": 1, "beat": 1}
    position = next(i for i in items if i["kind"] == "position")
    assert position["ref"] == {"string": 5, "fret": 0}
    assert position["ai"]["string"] == 6 and position["ai"]["fret"] == 5


def test_comparison_differences_are_capped_at_500_but_counted_fully(
    client: TestClient, engine: Engine
) -> None:
    bars = 150  # 600 notes, none of which the reference has
    beat = {"duration": 4, "notes": [{"string": 6, "fret": 1}]}
    score = {**_score(), "bars": [{"beats": [beat] * 4}] * bars}
    tab = _tab(engine, score=score)
    far = [
        {"onset": float(i), "pitch": 100, "string": 1, "fret": 0, "bar": i // 4 + 1}
        for i in range(600)
    ]
    client.put(f"/v1/tabs/{tab}/reference", json=_body(far))
    diffs = client.get(f"/v1/tabs/{tab}/comparison").json()["differences"]
    assert diffs["counts"] == {"position": 0, "missing": 600, "extra": 600, "timing": 0}
    assert len(diffs["items"]) == 500
    assert diffs["truncated"] is True


def _apply(client: TestClient, tab: str, base: str, **extra: Any) -> Any:
    body = {"base_revision_id": base, "kinds": ["position"], **extra}
    return client.post(f"/v1/tabs/{tab}/comparison/apply", json=body)


def test_apply_corrects_positions_in_a_new_current_revision(
    client: TestClient, engine: Engine
) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body(_moved(_notes())))
    base = _rev(client, tab)
    before = client.get(f"/v1/tabs/{tab}/comparison").json()
    assert before["position_accuracy"] == pytest.approx(0.75)
    resp = _apply(client, tab, base)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["applied"], body["skipped"]) == (MOVED, 0)
    revision = body["tab"]["revision"]
    assert revision["id"] != base and revision["source"] == "user"
    assert body["tab"]["id"] == tab and "alphatex" in body["tab"]
    assert _rev(client, tab) == revision["id"]
    assert len(client.get(f"/v1/tabs/{tab}/revisions").json()["items"]) == 2
    after = client.get(f"/v1/tabs/{tab}/comparison").json()
    assert after["position_accuracy"] == 1
    assert after["differences"]["counts"]["position"] == 0
    assert after["revision_id"] == revision["id"]
    # The earlier revision is kept as it was.
    old = client.get(f"/v1/tabs/{tab}/revisions/{base}").json()
    assert old["score"]["bars"][2]["beats"][3]["notes"][0]["string"] == 6


def test_apply_with_nothing_to_correct_creates_no_revision(
    client: TestClient, engine: Engine
) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body())
    base = _rev(client, tab)
    resp = _apply(client, tab, base)
    assert resp.status_code == 200
    assert (resp.json()["applied"], resp.json()["skipped"]) == (0, 0)
    assert resp.json()["tab"]["revision"]["id"] == base
    assert len(client.get(f"/v1/tabs/{tab}/revisions").json()["items"]) == 1


def test_apply_on_track_1_leaves_track_0_alone(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, score=_v3_score())
    rhythm = [
        {**n, "string": 3, "fret": n["fret"] - 5}  # string 4 fret 7+ -> string 3, same pitch
        for n in _track_notes(1)
    ]
    client.put(f"/v1/tabs/{tab}/reference?track=1", json=_body(rhythm))
    base = _rev(client, tab)
    resp = client.post(
        f"/v1/tabs/{tab}/comparison/apply?track=1",
        json={"base_revision_id": base, "kinds": ["position"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["applied"] == 2 * BARS
    tracks = resp.json()["tab"]["revision"]["score"]["tracks"]

    def positions(track: dict[str, Any]) -> list[tuple[int, int]]:
        return [
            (n["string"], n["fret"])
            for bar in track["bars"]
            for beat in bar["beats"]
            for n in beat["notes"]
        ]

    assert positions(tracks[0]) == positions(_v3_score()["tracks"][0])
    assert {n["string"] for b in tracks[1]["bars"] for x in b["beats"] for n in x["notes"]} == {3}


def test_apply_with_a_stale_base_is_409(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body(_moved(_notes())))
    base = _rev(client, tab)
    saved = client.post(
        f"/v1/tabs/{tab}/revisions", json={"base_revision_id": base, "score": _score()}
    )
    assert saved.status_code == 201
    resp = _apply(client, tab, base)
    assert resp.status_code == 409
    assert resp.json()["code"] == "revision_conflict"
    assert len(client.get(f"/v1/tabs/{tab}/revisions").json()["items"]) == 2


def test_apply_without_a_reference_is_404(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = _apply(client, tab, _rev(client, tab))
    assert resp.status_code == 404
    assert resp.json()["code"] == "reference_not_found"


def test_apply_with_a_missing_track_is_422(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine)
    resp = client.post(
        f"/v1/tabs/{tab}/comparison/apply?track=3",
        json={"base_revision_id": _rev(client, tab), "kinds": ["position"]},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_track"


@pytest.mark.parametrize("kinds", [["timing"], ["position", "missing"], ["nope"]])
def test_apply_only_supports_position(client: TestClient, engine: Engine, kinds: list[str]) -> None:
    tab = _tab(engine)
    client.put(f"/v1/tabs/{tab}/reference", json=_body(_moved(_notes())))
    resp = _apply(client, tab, _rev(client, tab), kinds=kinds)
    assert resp.status_code == 422
    assert resp.json()["code"] == "unsupported_correction"
    assert len(client.get(f"/v1/tabs/{tab}/revisions").json()["items"]) == 1


def test_apply_on_another_users_tab_is_404(client: TestClient, engine: Engine) -> None:
    tab = _tab(engine, "other@example.com")
    base = "00000000-0000-4000-8000-000000000000"
    resp = _apply(client, tab, base)
    assert resp.status_code == 404


def test_apply_needs_csrf_with_cookie_auth(
    engine: Engine, database_url: str, store: FakeStore, mailer: FakeMailer
) -> None:
    settings = _settings(database_url, dev_auth=False, session_cookie_secure=False)
    auth = TestClient(create_app(settings, store=store, mailer=mailer))
    with engine.begin() as conn:
        user = conn.execute(
            text("INSERT INTO users (email) VALUES ('apply@example.com') RETURNING id")
        ).scalar_one()
        tab = _tab_for(conn, str(user))
        base = str(
            conn.execute(
                text("SELECT current_revision_id FROM tabs WHERE id = :t"), {"t": tab}
            ).scalar_one()
        )
        conn.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at) "
                "VALUES (:u, :h, 'csrf-secret', now() + interval '1 day')"
            ),
            {"u": user, "h": hashlib.sha256(b"cookie").hexdigest()},
        )
    auth.cookies.set(SESSION_COOKIE, "cookie")
    headers = {"X-CSRF-Token": "csrf-secret"}
    auth.put(f"/v1/tabs/{tab}/reference", json=_body(_moved(_notes())), headers=headers)
    url = f"/v1/tabs/{tab}/comparison/apply"
    body = {"base_revision_id": base, "kinds": ["position"]}
    assert auth.post(url, json=body).status_code == 403
    assert auth.post(url, json=body, headers=headers).status_code == 201
