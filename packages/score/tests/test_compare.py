"""Comparison of a transcribed tab with the correct tab of the same song (M3, ADR-0009)."""

from fractions import Fraction

import pytest

from tabforge_score import Score
from tabforge_score.compare import (
    NoteEvent,
    compare,
    corrected_score,
    reference_tuning,
    score_events,
    tuning_name,
)

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


# differences and corrections ------------------------------------------------------------------


def _diffs(ai: list[NoteEvent], ref: list[NoteEvent]) -> list[tuple[str, float]]:
    return [(d.kind, d.onset) for d in compare(ai, ref, shifts=False).differences]


def test_score_events_set_the_beat_index() -> None:
    score = _score(
        [[_q(6, 0), _q(5, 2), _q(4, 2), _q(3, 1)], [_q(2, 0), _q(1, 0), _q(1, 3), _q(1, 5)]]
    )
    assert [e.beat_index for e in score_events(score)] == [0, 1, 2, 3, 0, 1, 2, 3]
    assert NoteEvent(onset=0, pitch=40, string=6, fret=0).beat_index is None


def test_identical_tabs_have_no_differences() -> None:
    notes = [_ev(0, 6, 0), _ev(1, 5, 2)]
    assert compare(notes, notes).differences == ()


def test_position_difference_lists_both_positions() -> None:
    ref = [_ev(0, 5, 0)]  # A2 is the open A string in the correct tab...
    ai = [
        NoteEvent(onset=0, pitch=45, string=6, fret=5, bar=2, beat_index=3)
    ]  # ...not low E fret 5
    (diff,) = compare(ai, ref, shifts=False).differences
    assert (diff.kind, diff.pitch, diff.bar) == ("position", 45, 1)
    assert (diff.ai_string, diff.ai_fret, diff.ref_string, diff.ref_fret) == (6, 5, 5, 0)
    assert (diff.ai_bar, diff.ai_beat, diff.onset_error) == (2, 3, 0)


def test_timing_difference_needs_more_than_an_eighth_of_a_quarter() -> None:
    ref = [_ev(0, 6, 0), _ev(1, 6, 0), _ev(2, 6, 0)]
    ai = [_ev(0.125, 6, 0), _ev(1.2, 6, 0), _ev(2, 6, 0)]
    diffs = compare(ai, ref, shifts=False).differences
    assert [(d.kind, d.onset) for d in diffs] == [("timing", 1)]
    assert diffs[0].onset_error == pytest.approx(0.2)
    assert (diffs[0].ai_string, diffs[0].ref_string) == (6, 6)


def test_position_is_reported_before_timing_when_both_differ() -> None:
    ai = [_ev(0.2, 6, 5)]
    ref = [_ev(0, 5, 0)]
    assert [d.kind for d in compare(ai, ref, shifts=False).differences] == ["position"]


def test_missing_and_extra_notes_are_ordered_by_onset() -> None:
    ref = [_ev(0, 6, 0), _ev(1, 6, 1), _ev(3, 6, 3)]
    ai = [_ev(0, 6, 0), _ev(2, 5, 0), _ev(3, 6, 3)]
    result = compare(ai, ref, shifts=False)
    assert [(d.kind, d.onset) for d in result.differences] == [("missing", 1), ("extra", 2)]
    missing, extra = result.differences
    assert (missing.ai_string, missing.ref_string, missing.ref_fret) == (None, 6, 1)
    assert (extra.ai_string, extra.ai_fret, extra.ref_string) == (5, 0, None)


def test_extra_onset_uses_scale_and_shift() -> None:
    ref = [_ev(4, 6, 0), _ev(6, 6, 1)]
    ai = [_ev(0, 6, 0), _ev(1, 6, 1), _ev(2.5, 5, 0)]
    result = compare(ai, ref)
    assert (result.scale, result.shift) == (2.0, 4.0)
    assert [(d.kind, d.onset) for d in result.differences] == [("extra", 9.0)]


def _reference(score: Score, track: int = 0) -> list[NoteEvent]:
    return [
        NoteEvent(e.onset, e.pitch, e.string, e.fret, e.bar) for e in score_events(score, track)
    ]


def _pad(*beats: dict[str, object]) -> list[dict[str, object]]:
    """One 4/4 bar: the given quarter beats, then quarter rests."""
    return [*beats, *({"duration": 4, "notes": []},) * (4 - len(beats))]


def test_corrected_score_moves_notes_to_the_reference_positions() -> None:
    wrong = _score([[_q(6, 5), _q(5, 5), _q(4, 2), _q(3, 0)]])  # A2, D3, E3, G3
    right = _score([[_q(5, 0), _q(4, 0), _q(4, 2), _q(3, 0)]])
    fixed, applied, skipped = corrected_score(wrong, 0, _reference(right))
    assert (applied, skipped) == (2, 0)
    assert fixed == right
    assert wrong.bars[0].beats[0].notes[0].string == 6  # input untouched


def test_corrected_score_moves_a_chord_note_without_touching_the_others() -> None:
    chord = {"duration": 1, "notes": [{"string": 6, "fret": 5}, {"string": 3, "fret": 2}]}
    right_chord = {"duration": 1, "notes": [{"string": 5, "fret": 0}, {"string": 3, "fret": 2}]}
    fixed, applied, _ = corrected_score(_score([[chord]]), 0, _reference(_score([[right_chord]])))
    assert applied == 1
    assert {(n.string, n.fret) for n in fixed.bars[0].beats[0].notes} == {(5, 0), (3, 2)}


def test_corrected_score_moves_tie_continuations_with_the_attack() -> None:
    def chain(string: int, fret: int) -> list[list[dict[str, object]]]:
        rest = {"duration": 4, "notes": []}
        return [
            [rest, rest, _q(string, fret), _q(string, fret, tie=True)],
            [_q(string, fret, tie=True), _q(string, fret, tie=True), rest, _q(string, fret)],
        ]

    wrong, right = _score(chain(6, 5)), _score(chain(5, 0))
    fixed, applied, skipped = corrected_score(wrong, 0, _reference(right))
    assert (applied, skipped) == (2, 0)  # the tied notes moved with their attacks
    assert fixed == right


def test_corrected_score_moves_chord_notes_together() -> None:
    chord = {"duration": 1, "notes": [{"string": 6, "fret": 5}, {"string": 5, "fret": 5}]}
    ref = [_ev(0, 5, 0), _ev(0, 4, 0)]  # A2 should be 5/0, D3 should be 4/0
    fixed, applied, skipped = corrected_score(_score([[chord]]), 0, ref)
    # 6/5 -> 5/0 needs string 5, which 5/5 -> 4/0 frees in the same step.
    assert (applied, skipped) == (2, 0)
    assert {(n.string, n.fret) for n in fixed.bars[0].beats[0].notes} == {(5, 0), (4, 0)}


def test_corrected_score_swaps_two_chord_notes() -> None:
    # G3 on 4/5 and B3 on 3/4; the correct tab has G3 on 3/0 and B3 on 4/9.
    chord = {"duration": 1, "notes": [{"string": 4, "fret": 5}, {"string": 3, "fret": 4}]}
    ref = [_ev(0, 3, 0), _ev(0, 4, 9)]
    fixed, applied, skipped = corrected_score(_score([[chord]]), 0, ref)
    assert (applied, skipped) == (2, 0)
    assert {(n.string, n.fret) for n in fixed.bars[0].beats[0].notes} == {(3, 0), (4, 9)}


def test_corrected_score_moves_an_extra_note_out_of_the_way() -> None:
    # A2 should be 5/0, but the transcription has an extra D3 on 5/5 (not in the correct tab).
    chord = {"duration": 1, "notes": [{"string": 6, "fret": 5}, {"string": 5, "fret": 5}]}
    fixed, applied, skipped = corrected_score(_score([[chord]]), 0, [_ev(0, 5, 0)])
    assert (applied, skipped) == (1, 0)
    # The extra D3 keeps its pitch on the nearest free string (4/0).
    assert {(n.string, n.fret) for n in fixed.bars[0].beats[0].notes} == {(5, 0), (4, 0)}


def test_corrected_score_skips_when_a_correct_note_holds_the_target_string() -> None:
    chord = {"duration": 1, "notes": [{"string": 6, "fret": 5}, {"string": 5, "fret": 5}]}
    ref = [_ev(0, 5, 0), _ev(0, 5, 5)]  # inconsistent: both on string 5; 5/5 is already right
    fixed, applied, skipped = corrected_score(_score([[chord]]), 0, ref)
    assert (applied, skipped) == (0, 1)
    assert {(n.string, n.fret) for n in fixed.bars[0].beats[0].notes} == {(6, 5), (5, 5)}


def test_corrected_score_skips_when_a_tie_chain_beat_uses_the_target_string() -> None:
    first = {"duration": 2, "notes": [{"string": 6, "fret": 5}]}
    second = {
        "duration": 2,
        "notes": [{"string": 6, "fret": 5, "tie": True}, {"string": 5, "fret": 3}],
    }
    wrong = _score([[first, second]])
    # 5/3 is right (in the correct tab), so it cannot make room for the held A2.
    fixed, applied, skipped = corrected_score(wrong, 0, [_ev(0, 5, 0), _ev(2, 5, 3)])
    assert (applied, skipped) == (0, 1)
    assert fixed == wrong


def test_corrected_score_skips_fret_out_of_range_and_pitch_changes() -> None:
    wrong = _score([_pad(_q(6, 5), _q(6, 7))])
    high = NoteEvent(onset=0, pitch=45, string=5, fret=0)
    low = NoteEvent(onset=1, pitch=47, string=4, fret=-3)  # impossible fret
    assert corrected_score(wrong, 0, [high, low])[1:] == (1, 1)
    # A2 at 5/0 (high) and B2 at 5/0 (other) disagree: the string-5 tuning cannot be told,
    # so the track keeps E standard and B2 cannot go to 5/0.
    other = NoteEvent(onset=1, pitch=47, string=5, fret=0)
    fixed, applied, skipped = corrected_score(wrong, 0, [high, other])
    assert fixed.tuning == STANDARD
    assert (applied, skipped) == (1, 1)


def test_corrected_score_in_v3_only_changes_the_chosen_track() -> None:
    bars = [{"beats": _pad(_q(6, 5))}]
    v3 = Score.model_validate(
        {
            "schema_version": 3,
            "tempo_bpm": 100,
            "time_signature": [4, 4],
            "tracks": [
                {"name": "Lead", "tuning": STANDARD, "bars": bars},
                {"name": "Rhythm", "tuning": STANDARD, "bars": bars},
            ],
        }
    )
    fixed, applied, _ = corrected_score(v3, 1, [_ev(0, 5, 0)])
    assert applied == 1
    assert fixed.schema_version == 3
    assert fixed.tracks[0] == v3.tracks[0]
    assert fixed.tracks[1].bars[0].beats[0].notes[0].string == 5


def test_a_corrected_score_compares_perfectly() -> None:
    wrong = _score([[_q(6, 5), _q(5, 5), _q(4, 2), _q(3, 0)]])
    reference = _reference(_score([[_q(5, 0), _q(4, 0), _q(4, 2), _q(3, 0)]]))
    fixed, _, _ = corrected_score(wrong, 0, reference)
    assert compare(score_events(fixed), reference).position_accuracy == 1


# tunings ---------------------------------------------------------------------------------------

D_STANDARD = [t - 2 for t in STANDARD]


def _ev_in(tuning: list[int], onset: float, string: int, fret: int) -> NoteEvent:
    return NoteEvent(onset=onset, pitch=tuning[string - 1] + fret, string=string, fret=fret)


def test_reference_tuning_is_read_from_the_notes() -> None:
    ref = [_ev_in(D_STANDARD, 0, 6, 0), _ev_in(D_STANDARD, 1, 5, 2), _ev_in(D_STANDARD, 2, 3, 4)]
    # Strings 1, 2 and 4 have no notes: they follow the same shift as the others (-2).
    assert reference_tuning(ref, STANDARD) == D_STANDARD


def test_reference_tuning_keeps_a_drop_tuning() -> None:
    drop_d = [*STANDARD[:5], 38]
    ref = [_ev_in(drop_d, 0, 6, 0), _ev_in(drop_d, 1, 5, 0), _ev_in(drop_d, 2, 4, 0)]
    assert reference_tuning(ref, STANDARD) == drop_d
    assert reference_tuning([], STANDARD) == STANDARD


def test_tuning_name() -> None:
    assert tuning_name(STANDARD) == "E standard"
    assert tuning_name(D_STANDARD) == "D standard"
    assert tuning_name([t - 1 for t in STANDARD]) == "Eb standard"
    assert tuning_name([*STANDARD[:5], 38]) == "Drop D"
    assert tuning_name([*D_STANDARD[:5], 36]) == "Drop C"
    assert tuning_name([64, 59, 55, 50, 45, 43]) == "G2 A2 D3 G3 B3 E4"  # low to high


def test_corrected_score_takes_the_tuning_of_the_correct_tab() -> None:
    # The transcription is in E standard; the correct tab plays the same notes in D standard.
    wrong = _score([_pad(_q(6, 5), _q(5, 7), _q(1, 0))])  # A2, E3, E4
    ref = [_ev_in(D_STANDARD, 0, 6, 7), _ev_in(D_STANDARD, 1, 4, 4)]  # A2 on 6/7, E3 on 4/4
    fixed, applied, skipped = corrected_score(wrong, 0, ref)
    assert (applied, skipped) == (2, 0)
    assert fixed.tuning == D_STANDARD
    beats = fixed.bars[0].beats
    assert [(n.string, n.fret) for b in beats[:3] for n in b.notes] == [(6, 7), (4, 4), (1, 2)]
    # Every note still sounds the same.
    assert [e.pitch for e in score_events(fixed, 0)] == [e.pitch for e in score_events(wrong, 0)]
    assert compare(score_events(fixed, 0), ref).position_accuracy == 1.0


def test_corrected_score_keeps_the_tuning_when_a_note_has_nowhere_to_go() -> None:
    # The correct tab is tuned up a tone; the extra open low E (40) cannot be played there.
    up = [t + 2 for t in STANDARD]
    wrong = _score([_pad(_q(6, 0), _q(5, 7))])  # E2 (extra), E3
    fixed, applied, skipped = corrected_score(wrong, 0, [_ev_in(up, 1, 5, 5), _ev_in(up, 2, 4, 0)])
    assert fixed.tuning == STANDARD
    assert (applied, skipped) == (0, 1)  # 5/5 in the old tuning is not E3
