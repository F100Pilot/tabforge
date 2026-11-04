import pytest

from tabforge_worker.arrange.quantize import TICKS_PER_BAR, TICKS_PER_BEAT, Event, quantize
from tabforge_worker.ports import NoteEvent

BEAT = 0.5  # 120 bpm
BEATS = [i * BEAT for i in range(16)]


def _n(onset: float, offset: float, pitch: int = 52, velocity: int = 90) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=offset, pitch=pitch, velocity=velocity)


def _ev(start: int, end: int, *pitches: int) -> Event:
    return Event(start=start, end=end, pitches=tuple(pitches))


def test_grid_constants() -> None:
    assert (TICKS_PER_BEAT, TICKS_PER_BAR) == (12, 48)


def test_straight_eighths_snap_with_jitter() -> None:
    onsets = [0.0, 0.26, 0.49, 0.77, 1.01]  # up to ±20 ms off the eighth grid
    notes = [_n(t, t + 0.2) for t in onsets]
    q = quantize(notes, BEATS)
    assert [e.start for e in q.events] == [0, 6, 12, 18, 24]
    # legato: each note lasts until the next onset; the last one until its own offset
    assert [e.end - e.start for e in q.events[:-1]] == [6, 6, 6, 6]
    assert q.total_ticks == TICKS_PER_BAR


def test_simultaneous_notes_form_one_event_and_duplicates_merge() -> None:
    notes = [_n(0.0, 0.5, 40), _n(0.01, 0.5, 47), _n(0.02, 0.5, 40), _n(0.5, 1.0, 52)]
    q = quantize(notes, BEATS)
    assert q.events[0] == _ev(0, 12, 40, 47)
    assert q.events[1].pitches == (52,)


def test_triplet_beat_is_detected() -> None:
    third = BEAT / 3
    notes = [_n(t, t + 0.1) for t in (0.0, third, 2 * third)] + [_n(0.5, 1.0)]
    q = quantize(notes, BEATS)
    assert 0 in q.triplet_beats
    assert [e.start for e in q.events] == [0, 4, 8, 12]


def test_two_onsets_on_eighths_stay_binary() -> None:
    q = quantize([_n(0.0, 0.2), _n(0.25, 0.45), _n(0.5, 1.0)], BEATS)
    assert 0 not in q.triplet_beats
    assert [e.start for e in q.events] == [0, 6, 12]


def test_long_silence_becomes_rest() -> None:
    # quarter note, then 2 beats of silence, then a note
    q = quantize([_n(0.0, 0.5), _n(1.5, 2.0)], BEATS)
    assert q.events[0] == _ev(0, 12, 52)
    assert q.events[1].start == 36


def test_short_gap_is_absorbed_legato() -> None:
    q = quantize([_n(0.0, 0.3), _n(0.5, 1.0)], BEATS)  # 200 ms gap < 1 beat
    assert q.events[0].end == 12


def test_bar_starts_at_beat_before_first_onset() -> None:
    q = quantize([_n(1.0, 1.5), _n(1.5, 2.0)], BEATS)  # first note on beat index 2
    assert q.events[0].start == 0


def test_beats_are_extrapolated_before_and_after() -> None:
    beats = [1.0, 1.5, 2.0]  # tracker found only three beats
    q = quantize([_n(0.0, 0.4), _n(2.75, 3.4)], beats)
    assert q.events[0].start == 0
    assert q.events[1].start == 66  # 2.75 s = beat 5.5 from 0.0 s at 0.5 s/beat


def test_tempo_from_beats() -> None:
    assert quantize([_n(0.0, 0.5)], BEATS).tempo_bpm == 120
    assert quantize([_n(0.0, 0.5)], [i * 0.75 for i in range(8)]).tempo_bpm == 80


def test_no_beats_falls_back_to_120_bpm() -> None:
    q = quantize([_n(0.0, 0.5), _n(0.5, 1.0)], [])
    assert q.tempo_bpm == 120
    assert [e.start for e in q.events] == [0, 12]


def test_empty_input_gives_one_empty_bar() -> None:
    q = quantize([], BEATS)
    assert q.events == ()
    assert q.total_ticks == TICKS_PER_BAR


def test_total_ticks_round_up_to_whole_bars() -> None:
    q = quantize([_n(0.0, 0.5), _n(2.0, 2.5)], BEATS)  # second note on beat 4 = bar 2
    assert q.total_ticks == 2 * TICKS_PER_BAR


@pytest.mark.parametrize("onset", [0.24, 0.26])
def test_onset_near_beat_boundary_snaps_to_nearest_grid_point(onset: float) -> None:
    q = quantize([_n(0.0, 0.2), _n(onset, 0.5), _n(0.5, 1.0)], BEATS)
    assert q.events[1].start == 6
