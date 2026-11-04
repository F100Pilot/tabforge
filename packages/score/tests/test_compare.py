"""Comparison of a transcribed tab with the correct tab of the same song (M3, ADR-0009)."""

from fractions import Fraction

import pytest

from tabforge_score import Score
from tabforge_score.compare import NoteEvent, compare, score_events

STANDARD = [64, 59, 55, 50, 45, 40]  # string 1 (high E) first


def _score(bars: list[list[dict[str, object]]], tempo: int = 100) -> Score:
    return Score.model_validate(
        {
            "schema_version": 2,
            "tempo_bpm": tempo,
            "time_signature": [4, 4],
            "tuning": STANDARD,
            "bars": [{"beats": beats} for beats in bars],
        }
    )


def _q(string: int, fret: int, *, tie: bool = False) -> dict[str, object]:
    return {"duration": 4, "notes": [{"string": string, "fret": fret, "tie": tie}]}


def _ev(onset: float, string: int, fret: int, bar: int = 1) -> NoteEvent:
    return NoteEvent(
        onset=onset, pitch=STANDARD[string - 1] + fret, string=string, fret=fret, bar=bar
    )


# score_events ---------------------------------------------------------------------------------


def test_events_have_onsets_in_quarter_notes_pitch_and_bar() -> None:
    score = _score(
        [[_q(6, 0), _q(5, 2), _q(4, 2), _q(3, 1)], [_q(2, 0), _q(1, 0), _q(1, 3), _q(1, 5)]]
    )
    events = score_events(score)
    assert [e.onset for e in events] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert events[0] == NoteEvent(onset=0, pitch=40, string=6, fret=0, bar=1)
    assert events[4].bar == 2 and events[4].pitch == 59


def test_tie_continuations_are_not_new_notes() -> None:
    score = _score([[_q(3, 2), _q(3, 2, tie=True), {"duration": 2, "notes": []}]])
    assert [(e.onset, e.pitch) for e in score_events(score)] == [(0, 57)]


def test_dots_and_triplets_move_the_onsets() -> None:
    dotted = {"duration": 4, "dots": 1, "notes": [{"string": 1, "fret": 0}]}
    eighth = {"duration": 8, "notes": [{"string": 1, "fret": 1}]}
    trip = [{"duration": 8, "tuplet": 3, "notes": [{"string": 2, "fret": f}]} for f in (0, 1, 3)]
    score = _score([[dotted, eighth, *trip, {"duration": 4, "notes": []}]])
    onsets = [e.onset for e in score_events(score)]
    assert onsets == [0, Fraction(3, 2), 2, Fraction(7, 3), Fraction(8, 3)]


def test_chords_give_one_event_per_note() -> None:
    chord = {"duration": 1, "notes": [{"string": 6, "fret": 3}, {"string": 5, "fret": 2}]}
    assert sorted(e.pitch for e in score_events(_score([[chord]]))) == [43, 47]


# compare --------------------------------------------------------------------------------------

RIFF = [
    _ev(i * 0.5, s, f) for i, (s, f) in enumerate([(6, 0), (6, 3), (5, 0), (5, 2), (4, 0), (4, 2)])
]


def test_identical_tabs_are_a_perfect_match() -> None:
    result = compare(RIFF, RIFF)
    assert result.recall == result.precision == result.f1 == 1.0
    assert result.position_accuracy == 1.0
    assert result.shift == 0 and result.scale == 1


def test_an_intro_in_the_reference_is_found_as_a_shift() -> None:
    reference = [NoteEvent(e.onset + 8, e.pitch, e.string, e.fret, e.bar + 2) for e in RIFF]
    result = compare(RIFF, reference)
    assert result.shift == 8
    assert result.recall == 1.0


def test_a_transcription_at_double_tempo_is_rescaled() -> None:
    doubled = [NoteEvent(e.onset * 2, e.pitch, e.string, e.fret, e.bar) for e in RIFF]
    result = compare(doubled, RIFF)
    assert result.scale == 0.5
    assert result.recall == 1.0


def test_same_notes_on_other_strings_count_as_found_but_wrong_position() -> None:
    # E2 riff played higher up: same pitches, different (string, fret) for half of the notes.
    moved = [
        NoteEvent(e.onset, e.pitch, e.string - 1, e.fret + 5, e.bar) if i % 2 else e
        for i, e in enumerate(RIFF)
    ]
    result = compare(moved, RIFF)
    assert result.recall == 1.0
    assert result.position_accuracy == pytest.approx(0.5)


def test_missing_and_extra_notes_lower_recall_and_precision() -> None:
    ai = [*RIFF[:4], _ev(10, 1, 12)]  # two notes missed, one invented
    result = compare(ai, RIFF)
    assert result.matched == 4
    assert result.recall == pytest.approx(4 / 6)
    assert result.precision == pytest.approx(4 / 5)


def test_small_timing_errors_are_tolerated_and_measured() -> None:
    late = [NoteEvent(e.onset + 0.1, e.pitch, e.string, e.fret, e.bar) for e in RIFF]
    result = compare(late, RIFF, shifts=False)
    assert result.recall == 1.0
    assert result.onset_error == pytest.approx(0.1)


def test_per_bar_results_follow_the_reference_bars() -> None:
    reference = [_ev(0, 6, 0, bar=1), _ev(4, 6, 3, bar=2), _ev(5, 5, 0, bar=2)]
    ai = [_ev(0, 6, 0), _ev(4, 6, 3)]
    result = compare(ai, reference, shifts=False)
    assert [(b.bar, b.reference_notes, b.matched) for b in result.bars] == [(1, 1, 1), (2, 2, 1)]


def test_empty_inputs_do_not_divide_by_zero() -> None:
    result = compare([], RIFF)
    assert result.recall == 0.0 and result.precision == 0.0 and result.f1 == 0.0
    assert result.position_accuracy is None
