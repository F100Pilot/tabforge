"""Fretting profiles on Postgres (ADR-0011): claiming stale ones, training data, results, use."""

import logging
import random
import threading
import time
import uuid
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_queue import RecordingPipeline, _job
from test_worker_loop import RecordingStore

from tabforge_worker import learning, profiles
from tabforge_worker.arrange.fretting import DEFAULT_WEIGHTS, Weights, candidate_positions
from tabforge_worker.learning import MIN_NOTES, TuningResult
from tabforge_worker.pipeline import PipelineResult, StageCallback, StubPipeline
from tabforge_worker.queue import ClaimedJob
from tabforge_worker.worker import WorkerConfig, refresh_profiles, run_forever, run_once

pytestmark = pytest.mark.db

Conn = psycopg.Connection[Any]
STANDARD = [64, 59, 55, 50, 45, 40]
HIGH = Weights(span=1.0, height=-0.1, move=0.25, open_move=0.0)


def _user(conn: Conn) -> uuid.UUID:
    row = conn.execute(
        "INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@example.com",)
    ).fetchone()
    assert row is not None
    user_id: uuid.UUID = row[0]
    return user_id


def _score(positions: list[tuple[int, int]], tracks: int = 1) -> dict[str, Any]:
    """Quarter notes, four per bar; a v3 score with `tracks` copies when tracks > 1."""
    bars = [
        {"beats": [{"duration": 4, "notes": [{"string": s, "fret": f}]} for s, f in chunk]}
        for chunk in (positions[i : i + 4] for i in range(0, len(positions), 4))
    ]
    if tracks == 1:
        return {
            "schema_version": 2,
            "tempo_bpm": 100,
            "time_signature": [4, 4],
            "tuning": STANDARD,
            "bars": bars,
        }
    return {
        "schema_version": 3,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tracks": [{"name": f"T{i}", "tuning": STANDARD, "bars": bars} for i in range(tracks)],
    }


def _tab(conn: Conn, user: uuid.UUID, score: dict[str, Any], source: str = "ai") -> uuid.UUID:
    row = conn.execute(
        "INSERT INTO tabs (owner_id, title) VALUES (%s, 'T') RETURNING id", (user,)
    ).fetchone()
    assert row is not None
    tab: uuid.UUID = row[0]
    _revision(conn, tab, score, source)
    return tab


def _revision(conn: Conn, tab: uuid.UUID, score: dict[str, Any], source: str) -> None:
    conn.execute(
        "WITH r AS (INSERT INTO tab_revisions (tab_id, score, source) VALUES (%s, %s, %s) "
        "RETURNING id) UPDATE tabs SET current_revision_id = (SELECT id FROM r) WHERE id = %s",
        (tab, Jsonb(score), source, tab),
    )


def _reference(conn: Conn, tab: uuid.UUID, notes: list[dict[str, Any]], track: int = 0) -> None:
    conn.execute(
        "INSERT INTO tab_references (tab_id, track_index, filename, track, notes) "
        "VALUES (%s, %s, 'song.gp5', 'Guitar', %s)",
        (tab, track, Jsonb(notes)),
    )


def _high_notes(count: int, seed: int) -> list[dict[str, Any]]:
    """A player who plays each note as high on the neck as fret 12 allows."""
    rng = random.Random(seed)  # noqa: S311 (test data, not crypto)
    notes, pitch = [], 57
    for i in range(count):
        pitch = max(50, min(69, pitch + rng.choice((-2, -1, 1, 2))))
        high = max(
            (p for p in candidate_positions(pitch, STANDARD) if p.fret <= 12), key=lambda p: p.fret
        )
        notes.append(
            {"onset": float(i), "pitch": pitch, "string": high.string, "fret": high.fret, "bar": 1}
        )
    return notes


def _stale(conn: Conn, user: uuid.UUID, age_s: int = 0) -> None:
    conn.execute(
        "INSERT INTO fretting_profiles (user_id, status, requested_at) "
        "VALUES (%s, 'stale', now() - make_interval(secs => %s))",
        (user, age_s),
    )


def _row(conn: Conn, user: uuid.UUID) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT * FROM fretting_profiles WHERE user_id = %s", (user,)).fetchone()
    assert row is not None
    return row


def _high_player(conn: Conn, tabs: int = 3, notes: int = 100) -> uuid.UUID:
    user = _user(conn)
    for t in range(tabs):
        tab = _tab(conn, user, _score([(6, 3)] * 4))
        _reference(conn, tab, _high_notes(notes, seed=t))
    return user


# Claiming and results --------------------------------------------------------------------------


def test_nothing_stale_returns_none(conn: Conn) -> None:
    user = _user(conn)
    conn.execute("INSERT INTO fretting_profiles (user_id, status) VALUES (%s, 'ready')", (user,))
    assert profiles.refresh_next(conn) is None


def test_refresh_learns_and_stores_accepted_weights(conn: Conn) -> None:
    user = _high_player(conn)
    _stale(conn, user)
    refreshed = profiles.refresh_next(conn)
    assert refreshed is not None
    assert (refreshed.user_id, refreshed.status) == (user, "ready")
    row = _row(conn, user)
    assert row["status"] == "ready"
    assert (row["tabs"], row["notes"]) == (3, 300)
    assert row["weights"] is not None and row["weights"]["height"] < DEFAULT_WEIGHTS.height
    assert row["tuned_accuracy"] > row["default_accuracy"]
    assert row["updated_at"] is not None
    assert profiles.accepted_weights(conn, user) == Weights(**row["weights"])
    assert profiles.refresh_next(conn) is None  # done


def test_too_little_data_is_stored_as_insufficient(conn: Conn) -> None:
    user = _high_player(conn, tabs=1, notes=MIN_NOTES + 50)
    _stale(conn, user)
    assert profiles.refresh_next(conn) is not None
    row = _row(conn, user)
    assert (row["status"], row["tabs"], row["notes"], row["weights"]) == (
        "insufficient",
        1,
        MIN_NOTES + 50,
        None,
    )
    assert row["default_accuracy"] is not None and row["tuned_accuracy"] is None
    assert profiles.accepted_weights(conn, user) is None


def test_oldest_request_is_refreshed_first(conn: Conn) -> None:
    newer, older = _user(conn), _user(conn)
    _stale(conn, newer, age_s=0)
    _stale(conn, older, age_s=60)
    first = profiles.refresh_next(conn)
    assert first is not None and first.user_id == older


def test_profile_locked_by_another_worker_is_skipped(conn: Conn, database_url: str) -> None:
    first, second = _user(conn), _user(conn)
    _stale(conn, first, age_s=60)
    _stale(conn, second, age_s=0)
    with psycopg.connect(database_url) as other:
        other.execute("SELECT 1 FROM fretting_profiles WHERE user_id = %s FOR UPDATE", (first,))
        refreshed = profiles.refresh_next(conn)
        assert refreshed is not None and refreshed.user_id == second
        assert profiles.refresh_next(conn) is None
        other.rollback()


def test_marked_again_while_tuning_stays_stale_with_the_new_numbers(
    conn: Conn, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _high_player(conn)
    _stale(conn, user, age_s=60)
    tune = learning.tune

    def tune_while_the_user_saves(tracks: Any) -> TuningResult:
        with psycopg.connect(database_url, autocommit=True) as api:  # the API marks it again
            api.execute(
                "UPDATE fretting_profiles SET status = 'stale', requested_at = now() "
                "WHERE user_id = %s",
                (user,),
            )
        return tune(tracks)

    monkeypatch.setattr(profiles, "tune", tune_while_the_user_saves)
    refreshed = profiles.refresh_next(conn)
    assert refreshed is not None and refreshed.status == "stale"
    row = _row(conn, user)
    assert row["status"] == "stale"
    assert (row["tabs"], row["notes"]) == (3, 300)


def test_a_failing_profile_goes_to_the_back_of_the_queue(
    conn: Conn, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    broken, fine = _user(conn), _high_player(conn, tabs=1, notes=10)
    _stale(conn, broken, age_s=60)
    _stale(conn, fine, age_s=30)
    before = _row(conn, broken)["requested_at"]
    tune = learning.tune

    def tune_or_crash(tracks: Any) -> TuningResult:
        if not tracks:
            raise RuntimeError("bug")
        return tune(tracks)

    monkeypatch.setattr(profiles, "tune", tune_or_crash)
    with caplog.at_level(logging.INFO, logger="tabforge_worker"):
        assert refresh_profiles(conn) == 0
    assert '"fretting_profile_failed"' in caplog.text
    assert _row(conn, broken)["requested_at"] > before
    with caplog.at_level(logging.INFO, logger="tabforge_worker"):
        assert refresh_profiles(conn, limit=1) == 1  # the other one goes first now
    assert _row(conn, fine)["status"] == "insufficient"
    assert '"fretting_profile_updated"' in caplog.text


# Training data ---------------------------------------------------------------------------------


def test_training_set_from_references_and_edited_revisions(conn: Conn) -> None:
    user = _user(conn)
    # Tab 1: a v3 tab with a reference on its track 1 only (and an edit, ignored).
    with_reference = _tab(conn, user, _score([(6, 3)] * 4, tracks=2))
    _reference(conn, with_reference, _high_notes(5, seed=1), track=1)
    _revision(conn, with_reference, _score([(6, 5)] * 4, tracks=2), "user")
    # Tab 2: edited by the user (two of four notes moved): its last edit is training data.
    edited = _tab(conn, user, _score([(6, 3), (6, 5), (5, 3), (5, 5)]))
    _revision(conn, edited, _score([(6, 3), (6, 5), (6, 7), (5, 5)]), "user")
    _revision(conn, edited, _score([(6, 3), (6, 5), (6, 8), (6, 10)]), "user")
    # Tab 3: saved by the user without changing a note; tab 4: never edited.
    same = _score([(6, 3), (6, 5)])
    _revision(conn, _tab(conn, user, same), same, "user")
    _tab(conn, user, _score([(6, 1)]))
    # Another user's reference is never read.
    _reference(conn, _tab(conn, _user(conn), _score([(6, 3)])), _high_notes(5, seed=2))

    tracks = profiles.load_training_set(conn, user)
    by_tab = {t.tab: t for t in tracks}
    assert set(by_tab) == {str(with_reference), str(edited)}
    assert by_tab[str(with_reference)].notes == 5
    assert [(p.string, p.fret) for e in by_tab[str(edited)].events for p in e.positions] == [
        (6, 3),
        (6, 5),
        (6, 8),
        (6, 10),
    ]


def test_reference_tuning_comes_from_the_tabs_track(conn: Conn) -> None:
    user = _user(conn)
    drop_d = [64, 59, 55, 50, 45, 38]
    score = _score([(6, 3)] * 4, tracks=2)
    score["tracks"][1]["tuning"] = drop_d
    tab = _tab(conn, user, score)
    # The reference only plays string 1, so the low string's tuning comes from the track.
    _reference(conn, tab, [{"onset": 0.0, "pitch": 65, "string": 1, "fret": 1, "bar": 1}], 1)
    (track,) = profiles.load_training_set(conn, user)
    assert track.tuning == tuple(drop_d)


# Using the weights -----------------------------------------------------------------------------


def test_accepted_weights_only_while_ready(conn: Conn) -> None:
    user = _user(conn)
    assert profiles.accepted_weights(conn, user) is None
    conn.execute(
        "INSERT INTO fretting_profiles (user_id, status, weights) VALUES (%s, 'ready', %s)",
        (user, Jsonb({"span": 1.0, "height": -0.1, "move": 0.25, "open_move": 0.0})),
    )
    assert profiles.accepted_weights(conn, user) == HIGH
    conn.execute("UPDATE fretting_profiles SET status = 'stale' WHERE user_id = %s", (user,))
    assert profiles.accepted_weights(conn, user) is None


class JobRecordingPipeline(RecordingPipeline):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[ClaimedJob] = []

    def process(self, job: ClaimedJob, on_stage: StageCallback) -> PipelineResult:
        self.jobs.append(job)
        return super().process(job, on_stage)


def test_run_once_gives_the_pipeline_the_owners_weights(conn: Conn, database_url: str) -> None:
    job_id = _job(conn)
    owner = conn.execute(
        "SELECT a.user_id FROM jobs j JOIN audio_assets a ON a.id = j.audio_id WHERE j.id = %s",
        (job_id,),
    ).fetchone()
    assert owner is not None
    conn.execute(
        "INSERT INTO fretting_profiles (user_id, status, weights) VALUES (%s, 'ready', %s)",
        (owner[0], Jsonb({"span": 1.0, "height": -0.1, "move": 0.25, "open_move": 0.0})),
    )
    _job(conn)  # another user, without a profile
    pipeline = JobRecordingPipeline()
    assert run_once(conn, WorkerConfig(database_url), pipeline)
    assert run_once(conn, WorkerConfig(database_url), pipeline)
    assert {job.id: job.weights for job in pipeline.jobs}[job_id] == HIGH
    assert [job.weights for job in pipeline.jobs if job.id != job_id] == [None]


def test_run_forever_refreshes_stale_profiles_at_startup(conn: Conn, database_url: str) -> None:
    user = _high_player(conn, tabs=1, notes=10)
    _stale(conn, user)
    config = WorkerConfig(database_url, poll_interval_s=0.05)
    stop = threading.Event()
    thread = threading.Thread(
        target=run_forever, args=(config, stop, StubPipeline(), RecordingStore()), daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while _row(conn, user)["status"] == "stale" and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert _row(conn, user)["status"] == "insufficient"
