"""Score assembly: one guitar (v2) or Lead + Rhythm tracks (v3, ADR-0010)."""

import pytest
from tabforge_score import Score, to_alphatex

from tabforge_worker.arrange.layout import build_tracks_score
from tabforge_worker.arrange.quantize import TICKS_PER_BAR, quantize
from tabforge_worker.arrange.tracks import arrange_guitar, arrange_lead_rhythm
from tabforge_worker.ports import NoteEvent

STANDARD = (64, 59, 55, 50, 45, 40)
BEATS = [0.5 * i for i in range(64)]


def _n(onset: float, pitch: int, length: float = 0.25) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=onset + length, pitch=pitch, velocity=90)


def _chords(start: float, count: int) -> list[NoteEvent]:
    notes = []
    for k in range(count):
        t = start + 0.25 * k
        notes += [_n(t, 40), _n(t + 0.01, 47), _n(t + 0.02, 52)]
    return notes


def _attacks(score: Score, track: int) -> list[int]:
    chosen = score.track_list()[track]
    return [
        chosen.tuning[n.string - 1] + n.fret
        for bar in chosen.bars
        for beat in bar.beats
        for n in beat.notes
        if not n.tie
    ]


def test_guitar_stem_stays_v2() -> None:
    score = arrange_guitar([_n(0.0, 64), _n(0.5, 69)], BEATS, STANDARD)
    data = score.model_dump(mode="json")
    assert data["schema_version"] == 2
    assert "tracks" not in data
    assert _attacks(score, 0) == [64, 69]


def test_mix_gives_lead_and_rhythm_with_equal_bars() -> None:
    chords = _chords(0.0, 8)  # bar 1: power chords
    melody = [_n(2.0 + 0.5 * k, p, 0.5) for k, p in enumerate((72, 74, 76, 79, 76, 74, 72, 71))]
    score = arrange_lead_rhythm(chords + melody, BEATS, None, STANDARD)

    data = score.model_dump(mode="json")
    assert data["schema_version"] == 3
    assert set(data) == {"schema_version", "tempo_bpm", "time_signature", "tracks"}
    Score.model_validate(data)
    lead, rhythm = score.track_list()
    assert (lead.name, rhythm.name) == ("Lead", "Rhythm")
    assert len(lead.bars) == len(rhythm.bars) == 3  # melody runs to 6.0 s = end of bar 3
    assert _attacks(score, 0) == [72, 74, 76, 79, 76, 74, 72, 71]
    assert sorted(_attacks(score, 1)) == sorted(n.pitch for n in chords)
    # Rhythm is all rests after its chords; Lead starts with a rest bar (same grid, same bar 1).
    assert all(not beat.notes for bar in rhythm.bars[1:] for beat in bar.beats)
    assert all(not beat.notes for beat in lead.bars[0].beats)
    tex = to_alphatex(score, "t")
    assert '\\track "Lead"' in tex and '\\track "Rhythm"' in tex


def test_ambiguous_notes_appear_in_both_tracks() -> None:
    riff = [_n(0.25 * k, p) for k, p in enumerate((57, 59, 60, 62) * 2)]
    score = arrange_lead_rhythm(riff, BEATS, [0.2] * len(riff), STANDARD)
    assert _attacks(score, 0) == _attacks(score, 1) == [n.pitch for n in riff]


def test_empty_side_is_all_rests() -> None:
    score = arrange_lead_rhythm(_chords(0.0, 4), BEATS, None, STANDARD)
    lead, rhythm = score.track_list()
    assert _attacks(score, 0) == []
    assert len(_attacks(score, 1)) == 12
    assert len(lead.bars) == len(rhythm.bars) == 1
    assert all(not beat.notes for bar in lead.bars for beat in bar.beats)


def test_no_notes_at_all() -> None:
    score = arrange_lead_rhythm([], BEATS, None, STANDARD)
    assert [t.name for t in score.track_list()] == ["Lead", "Rhythm"]


def test_quantize_span_fixes_bar_one() -> None:
    late = [_n(2.0, 72)]
    alone = quantize(late, BEATS)
    shared = quantize(late, BEATS, span=(0.0, 2.5))
    assert alone.events[0].start == 0  # bar 1 starts at the beat of the first own note
    assert shared.events[0].start == TICKS_PER_BAR  # 4 beats after the span start = bar 2
    empty = quantize([], [0.0, 0.6, 1.2], span=(0.0, 1.0))
    assert empty.events == () and empty.tempo_bpm == 100


def test_build_tracks_score_rejects_mismatched_tracks() -> None:
    a = quantize([_n(0.0, 64)], BEATS)
    b = quantize([_n(0.0, 64, 3.0)], BEATS)  # 2 bars
    assert a.total_ticks != b.total_ticks
    with pytest.raises(ValueError):
        build_tracks_score([("Lead", a, []), ("Rhythm", b, [])], STANDARD)
    with pytest.raises(ValueError):
        build_tracks_score([], STANDARD)
