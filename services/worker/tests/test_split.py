"""Lead/Rhythm roles from note features (ADR-0010): pure rules, no audio."""

import pytest

from tabforge_worker.arrange.split import (
    BOTH_MARGIN,
    NoteFeatures,
    Role,
    assign_roles,
    note_features,
    note_score,
    shape_groups,
    split_notes,
    stereo_usable,
)
from tabforge_worker.ports import NoteEvent

BEAT = 0.5
BEATS = [i * BEAT for i in range(64)]


def _n(onset: float, pitch: int, length: float = 0.25) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=onset + length, pitch=pitch, velocity=90)


def _power_chords(start: float, count: int, root: int = 40, step: float = 0.25) -> list[NoteEvent]:
    """Root + fifth + octave, struck every `step` seconds (with 10 ms strum spread)."""
    notes = []
    for k in range(count):
        t = start + k * step
        notes += [_n(t, root, step), _n(t + 0.01, root + 7, step), _n(t + 0.02, root + 12, step)]
    return notes


def _roles(notes: list[NoteEvent], side: list[float] | None = None) -> list[Role]:
    return assign_roles(notes, note_features(notes, side), BEATS)


def test_shape_groups_keep_chords_and_separate_a_lead_note_above() -> None:
    notes = [*_power_chords(0.0, 1), _n(0.0, 76)]  # E2 B2 E3 + E5 on the same onset
    groups = shape_groups(notes)
    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[0]
    features = note_features(notes, None)
    assert [f.polyphony for f in features] == [3, 3, 3, 1]


def test_open_chord_is_one_shape() -> None:
    e_major = [_n(0.0 + 0.008 * k, p) for k, p in enumerate((40, 47, 52, 56, 59, 64))]
    assert len(set(shape_groups(e_major))) == 1


def test_repeats_count_same_pitch_nearby() -> None:
    notes = [_n(0.25 * k, 40) for k in range(4)] + [_n(3.0, 40)]
    repeats = [f.repeats for f in note_features(notes, None)]
    assert repeats == [3, 3, 3, 3, 0]


def test_note_score_signs() -> None:
    chord = NoteFeatures(side_ratio=0.45, polyphony=3, pitch=40, duration_s=0.25, repeats=4)
    melody = NoteFeatures(side_ratio=0.02, polyphony=1, pitch=72, duration_s=0.5, repeats=0)
    assert note_score(chord, use_side=True) > 2
    assert note_score(melody, use_side=True) < -1.5
    # Without stereo, the role rules alone still point the same way.
    assert note_score(chord, use_side=False) > 1
    assert note_score(melody, use_side=False) <= -1


def test_chords_are_rhythm_and_high_single_notes_are_lead() -> None:
    chords = _power_chords(0.0, 16)  # two bars of eighth-note power chords
    melody = [_n(4.0 + 0.5 * k, p, 0.5) for k, p in enumerate((64, 67, 69, 71, 72, 71, 69, 67))]
    notes = chords + melody
    roles = _roles(notes)
    assert roles[: len(chords)] == ["rhythm"] * len(chords)
    assert roles[len(chords) :] == ["lead"] * len(melody)


def test_simultaneous_chords_and_melody_are_split() -> None:
    chords = _power_chords(0.0, 16)
    melody = [_n(0.5 * k, p, 0.5) for k, p in enumerate((76, 74, 72, 74, 76, 79, 76, 74))]
    side = [0.45] * len(chords) + [0.03] * len(melody)
    roles = _roles(chords + melody, side)
    assert roles[: len(chords)] == ["rhythm"] * len(chords)
    assert roles[len(chords) :] == ["lead"] * len(melody)


def test_smoothing_keeps_one_odd_note_in_its_line() -> None:
    # C4 alone would score 0 (single, mid register, no stereo): its neighbours pull it to Lead.
    notes = [_n(0.5 * k, p, 0.5) for k, p in enumerate((64, 67, 60, 65, 69))]
    alone = note_score(note_features([notes[2]], None)[0], use_side=False)
    assert abs(alone) < BOTH_MARGIN
    assert _roles(notes) == ["lead"] * 5


def test_notes_of_one_chord_share_a_role() -> None:
    # A low chord with a high top note: the top note alone leans Lead, the shape decides.
    chord = [_n(0.0, 45), _n(0.01, 52), _n(0.02, 57), _n(0.03, 64)]
    assert len(set(_roles(chord))) == 1


def test_ambiguous_passage_goes_to_both() -> None:
    # Mid-register single-note riff, half-way between centre and sides: no clear evidence.
    riff = [_n(0.25 * k, p) for k, p in enumerate((57, 59, 60, 62) * 2)]
    roles = _roles(riff, [0.2] * len(riff))
    assert roles == ["both"] * len(riff)
    lead, rhythm = split_notes(riff, roles)
    assert lead == riff and rhythm == riff


def test_low_riff_in_unison_goes_to_both() -> None:
    # Lead in the centre + doubled rhythm at the sides on the same low riff: side ratio ~0.25.
    riff = [_n(0.25 * k, p) for k, p in enumerate((40, 40, 43, 45) * 4)]
    assert _roles(riff, [0.25] * len(riff)) == ["both"] * len(riff)
    # The same riff only at the sides, or with no stereo information: Rhythm.
    assert _roles(riff, [0.45] * len(riff)) == ["rhythm"] * len(riff)
    assert _roles(riff) == ["rhythm"] * len(riff)


def test_high_melody_stays_lead_with_some_side_energy() -> None:
    # A centred lead picks up some side energy from stereo reverb: still Lead, not unison.
    melody = [_n(0.5 * k, p, 0.5) for k, p in enumerate((72, 74, 76, 79) * 2)]
    assert _roles(melody, [0.2] * len(melody)) == ["lead"] * len(melody)


def test_side_energy_decides_a_mid_register_riff_when_stereo_is_usable() -> None:
    # The same riff twice, 4 s apart: first in the centre, then wide (doubled, panned L/R).
    riff = [_n(0.25 * k, p) for k, p in enumerate((57, 59, 60, 62) * 2)]
    later = [_n(n.onset_s + 4.0, n.pitch) for n in riff]
    roles = _roles(riff + later, [0.0] * len(riff) + [0.45] * len(later))
    assert roles == ["lead"] * len(riff) + ["rhythm"] * len(later)


def test_identical_channels_disable_the_side_feature() -> None:
    riff = [_n(0.25 * k, p) for k, p in enumerate((57, 59, 60, 62) * 2)]
    flat = note_features(riff, [0.001] * len(riff))
    assert not stereo_usable(flat)
    assert not stereo_usable(note_features(riff, None))
    assert stereo_usable(note_features(riff, [0.0] * 4 + [0.3] * 4))
    # Near-zero side everywhere must not read as "everything is centred, so Lead".
    assert _roles(riff, [0.001] * len(riff)) == ["both"] * len(riff)


def test_split_notes_puts_both_in_each_list() -> None:
    notes = [_n(0.0, 40), _n(0.5, 72), _n(1.0, 57)]
    lead, rhythm = split_notes(notes, ["rhythm", "lead", "both"])
    assert lead == [notes[1], notes[2]]
    assert rhythm == [notes[0], notes[2]]


def test_length_mismatches_are_rejected() -> None:
    notes = [_n(0.0, 40)]
    with pytest.raises(ValueError):
        note_features(notes, [0.1, 0.2])
    with pytest.raises(ValueError):
        assign_roles(notes, [], BEATS)
    with pytest.raises(ValueError):
        split_notes(notes, [])


def test_no_notes() -> None:
    assert assign_roles([], [], BEATS) == []
    assert assign_roles([], [], []) == []


def test_works_without_beats() -> None:
    notes = _power_chords(0.0, 4)
    assert set(assign_roles(notes, note_features(notes, None), [])) == {"rhythm"}
