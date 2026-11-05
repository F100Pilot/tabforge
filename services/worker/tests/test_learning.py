"""Learning the string/fret weights from a player's correct tabs (ADR-0011), without a database."""

import random
import time
from typing import Any

import pytest
from tabforge_score.compare import NoteEvent

from tabforge_worker.arrange.fretting import (
    DEFAULT_WEIGHTS,
    Position,
    Weights,
    assign_positions,
    candidate_positions,
)
from tabforge_worker.learning import (
    GRID,
    MIN_NOTES,
    MIN_TABS,
    ReferenceRow,
    RevisionRow,
    TrainingEvent,
    TrainingTrack,
    build_training_set,
    choose,
    group_events,
    infer_tuning,
    tune,
)

STANDARD = (64, 59, 55, 50, 45, 40)


def _note(
    onset: float, string: int, fret: int, tuning: tuple[int, ...] = STANDARD
) -> dict[str, Any]:
    return {
        "onset": onset,
        "pitch": tuning[string - 1] + fret,
        "string": string,
        "fret": fret,
        "bar": 1 + int(onset // 4),
    }


def _score(frets: list[list[tuple[int, int]]], version: int = 2) -> dict[str, Any]:
    """One bar per item of `frets`; each (string, fret) is a quarter note."""
    bars = [
        {"beats": [{"duration": 4, "notes": [{"string": s, "fret": f}]} for s, f in bar]}
        for bar in frets
    ]
    if version == 2:
        return {
            "schema_version": 2,
            "tempo_bpm": 100,
            "time_signature": [4, 4],
            "tuning": list(STANDARD),
            "bars": bars,
        }
    return {
        "schema_version": 3,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tracks": [
            {"name": "Lead", "tuning": list(STANDARD), "bars": bars},
            {"name": "Rhythm", "tuning": list(STANDARD), "bars": bars},
        ],
    }


RIFF = [[(6, 3), (6, 5), (5, 3), (5, 5)]]
RIFF_HIGH = [[(6, 3), (6, 5), (6, 8), (6, 10)]]  # the same pitches, two of them moved up


# Training set --------------------------------------------------------------------------------


def test_notes_with_the_same_onset_form_one_event_in_time_order() -> None:
    notes = [_note(1.0, 1, 0), _note(0.0, 6, 0), _note(0.0, 5, 2), _note(0.0, 4, 2)]
    events = group_events(NoteEvent(**n) for n in notes)
    assert events == (
        TrainingEvent((40, 47, 52), (Position(6, 0), Position(5, 2), Position(4, 2))),
        TrainingEvent((64,), (Position(1, 0),)),
    )


def test_tuning_is_read_from_the_reference_notes() -> None:
    drop_d = (64, 59, 55, 50, 45, 38)
    rows = [_note(0, 6, 0, drop_d), _note(1, 6, 5, drop_d), _note(2, 1, 3, drop_d)]
    notes = [NoteEvent(**n) for n in rows]
    assert infer_tuning(notes, STANDARD) == drop_d
    assert infer_tuning([], STANDARD) == STANDARD


def test_a_reference_gives_one_track_with_its_notes() -> None:
    notes = [_note(i, 6, 3) for i in range(5)]
    (track,) = build_training_set([ReferenceRow("t1", 0, notes, list(STANDARD))], [])
    assert track.tab == "t1"
    assert track.tuning == STANDARD
    assert len(track.events) == 5
    assert track.notes == 5


def test_reference_without_a_usable_tuning_falls_back_to_standard() -> None:
    (track,) = build_training_set([ReferenceRow("t1", 1, [_note(0, 2, 1)], None)], [])
    assert track.tuning == STANDARD


def test_an_edited_revision_gives_its_notes_per_track() -> None:
    rows = [RevisionRow("t1", _score(RIFF_HIGH, 3), _score(RIFF, 3))]
    tracks = build_training_set([], rows)
    assert [t.tab for t in tracks] == ["t1", "t1"]
    assert [e.positions for e in tracks[0].events] == [
        (Position(6, 3),),
        (Position(6, 5),),
        (Position(6, 8),),
        (Position(6, 10),),
    ]


def test_a_revision_equal_to_the_ai_tab_teaches_nothing() -> None:
    same = RevisionRow("t1", _score(RIFF), _score(RIFF))
    assert build_training_set([], [same]) == []
    never_edited = RevisionRow("t2", None, _score(RIFF))
    assert build_training_set([], [never_edited]) == []


def test_the_reference_wins_over_the_revisions_of_the_same_tab() -> None:
    reference = ReferenceRow("t1", 0, [_note(0, 6, 3)], list(STANDARD))
    revision = RevisionRow("t1", _score(RIFF_HIGH), _score(RIFF))
    tracks = build_training_set([reference], [revision])
    assert [t.notes for t in tracks] == [1]


def test_unreadable_rows_are_skipped() -> None:
    bad_reference = ReferenceRow("t1", 0, [{"onset": 0}], list(STANDARD))
    bad_revision = RevisionRow("t2", {"schema_version": 9}, _score(RIFF))
    good = ReferenceRow("t3", 0, [_note(0, 6, 3)], list(STANDARD))
    assert [t.tab for t in build_training_set([bad_reference, good], [bad_revision])] == ["t3"]


def test_training_set_keeps_whole_tabs_up_to_the_note_limit() -> None:
    rows = [ReferenceRow(f"t{i}", 0, [_note(j, 6, 3) for j in range(10)], None) for i in range(5)]
    tracks = build_training_set(rows, [], max_notes=25)
    assert [t.tab for t in tracks] == ["t0", "t1"]


# Choosing the weights ------------------------------------------------------------------------


def test_choose_in_sample_with_two_tabs() -> None:
    choice = choose([[10, 15], [10, 12]], notes=40, cross_validate=False)
    assert (choice.index, choice.accepted) == (1, True)
    assert choice.default_accuracy == pytest.approx(0.5)
    assert choice.tuned_accuracy == pytest.approx(27 / 40)


def test_choose_prefers_the_default_on_ties() -> None:
    choice = choose([[10, 10], [5, 5]], notes=20, cross_validate=False)
    assert (choice.index, choice.accepted) == (0, False)


def test_cross_validation_accepts_weights_that_help_every_held_out_tab() -> None:
    choice = choose([[10, 20], [10, 20], [10, 20]], notes=90, cross_validate=True)
    assert (choice.index, choice.accepted) == (1, True)
    assert choice.default_accuracy == pytest.approx(30 / 90)
    assert choice.tuned_accuracy == pytest.approx(60 / 90)


def test_cross_validation_rejects_weights_that_only_fit_one_tab() -> None:
    # In-sample the second weights win (66 vs 40), but only because of tab 0: chosen without
    # it, they lose it, and on tabs 1 and 2 they are worse than the default.
    choice = choose([[0, 30], [20, 18], [20, 18]], notes=90, cross_validate=True)
    assert choice.accepted is False
    assert choice.default_accuracy == pytest.approx(40 / 90)
    assert choice.tuned_accuracy == pytest.approx(36 / 90)


# End to end ----------------------------------------------------------------------------------


def _high_player_tracks(tabs: int, notes_per_tab: int, seed: int = 3) -> list[TrainingTrack]:
    """A player who plays every note as high on the neck as fret 12 allows."""
    rng = random.Random(seed)  # noqa: S311 (test data, not crypto)
    tracks = []
    for t in range(tabs):
        events = []
        pitch = 57
        for _ in range(notes_per_tab):
            pitch = max(50, min(69, pitch + rng.choice((-2, -1, 1, 2))))
            high = max(
                (p for p in candidate_positions(pitch, STANDARD) if p.fret <= 12),
                key=lambda p: p.fret,
            )
            events.append(TrainingEvent((pitch,), (high,)))
        tracks.append(TrainingTrack(f"t{t}", STANDARD, tuple(events)))
    return tracks


def _default_player_tracks(tabs: int, notes_per_tab: int) -> list[TrainingTrack]:
    tracks = []
    for track in _high_player_tracks(tabs, notes_per_tab):
        events = [(e.pitches, (90,) * len(e.pitches)) for e in track.events]
        fretted = assign_positions(events, STANDARD)
        tracks.append(
            TrainingTrack(
                track.tab,
                STANDARD,
                tuple(TrainingEvent(f.pitches, f.positions) for f in fretted),
            )
        )
    return tracks


def test_grid_is_bounded_and_holds_the_default() -> None:
    assert len(GRID) <= 300
    assert DEFAULT_WEIGHTS in GRID
    assert len(set(GRID)) == len(GRID)


def test_learns_a_player_who_prefers_high_positions() -> None:
    result = tune(_high_player_tracks(tabs=4, notes_per_tab=100))
    assert result.status == "ready"
    assert (result.tabs, result.notes) == (4, 400)
    assert result.weights is not None
    assert result.weights.height < DEFAULT_WEIGHTS.height
    assert result.default_accuracy is not None and result.tuned_accuracy is not None
    assert result.tuned_accuracy > result.default_accuracy + 0.2


def test_keeps_the_default_for_a_player_who_already_matches_it() -> None:
    result = tune(_default_player_tracks(tabs=3, notes_per_tab=100))
    assert result.status == "ready"
    assert result.weights is None
    assert result.default_accuracy == pytest.approx(1.0)


def test_too_few_notes_is_insufficient() -> None:
    result = tune(_high_player_tracks(tabs=3, notes_per_tab=(MIN_NOTES - 1) // 3))
    assert result.status == "insufficient"
    assert result.weights is None
    assert result.tuned_accuracy is None
    assert result.default_accuracy is not None  # measured, so the UI can show it
    assert result.notes == (MIN_NOTES - 1) // 3 * 3


def test_one_tab_is_insufficient_however_many_notes() -> None:
    result = tune(_high_player_tracks(tabs=MIN_TABS - 1, notes_per_tab=1000))
    assert (result.status, result.tabs, result.weights) == ("insufficient", 1, None)


def test_no_data_is_insufficient_without_accuracies() -> None:
    result = tune([])
    assert (result.status, result.tabs, result.notes) == ("insufficient", 0, 0)
    assert (result.default_accuracy, result.tuned_accuracy) == (None, None)


def test_two_tabs_are_judged_in_sample() -> None:
    result = tune(_high_player_tracks(tabs=2, notes_per_tab=150))
    assert result.status == "ready"
    assert result.weights is not None


def test_tuning_5000_notes_takes_seconds() -> None:
    started = time.perf_counter()
    result = tune(_high_player_tracks(tabs=10, notes_per_tab=500))
    elapsed = time.perf_counter() - started
    assert result.notes == 5000
    assert elapsed < 30  # about 4 s on a laptop core; generous for slow CI runners


def test_weights_round_trip_through_json() -> None:
    from tabforge_worker.learning import weights_from_json, weights_to_json

    weights = Weights(span=2.0, height=-0.1, move=0.25, open_move=0.0)
    assert weights_from_json(weights_to_json(weights)) == weights
    assert weights_from_json(None) is None
    assert weights_from_json({"span": 1}) is None
    assert weights_from_json("nonsense") is None
