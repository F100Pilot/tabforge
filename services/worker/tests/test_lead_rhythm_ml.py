"""Lead/Rhythm split end to end on a synthetic band-like guitar stem (ml extra, ADR-0010).

The stem has two rhythm takes of eighth-note power chords, one hard left and one hard right
(slightly detuned, ~10 ms apart, as two real takes would be), and a lead melody in the centre,
partly at the same time as the chords. Basic Pitch transcribes it (as mono), librosa tracks the
beats, the stereo analyzer measures each note, and the real arrange path builds the v3 Score.

The numbers are printed (`pytest -m ml -s`) and recorded in docs/eval/M3-lead-rhythm.md. This
says the rules work on clean synthetic audio only, not on real songs.
"""

import wave
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from tabforge_worker.ports import NoteEvent

pytestmark = pytest.mark.ml

SR = 44100
BEAT_S = 0.5  # 120 bpm
EIGHTH_S = BEAT_S / 2
ONSET_TOLERANCE_S = 0.05
# Power chords (root, fifth, octave): one per bar, struck on every eighth note.
CHORD_ROOTS = (40, 45, 43, 38)  # E2, A2, G2, D2
CHORD_BARS = (0, 1, 2, 3, 4, 5, 6, 7)  # 8 bars; the melody plays over bars 2-3 and 6-7
MELODY = (  # (bar, beat, beats long, MIDI pitch), centred
    (2, 0, 1, 76),
    (2, 1, 1, 79),
    (2, 2, 2, 81),
    (3, 0, 1, 83),
    (3, 1, 1, 81),
    (3, 2, 1, 79),
    (3, 3, 1, 76),
    (6, 0, 2, 74),
    (6, 2, 1, 76),
    (6, 3, 1, 79),
    (7, 0, 1, 78),
    (7, 1, 1, 76),
    (7, 2, 2, 74),
)


UNISON_RIFF = (40, 40, 43, 45, 40, 40, 47, 45) * 4  # E2 riff, eighth notes, 4 bars
STANDARD = (64, 59, 55, 50, 45, 40)


def _hz(pitch: float) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def _pluck(pitch: float, seconds: float, harmonics: int, decay: float, phase: float):  # type: ignore[no-untyped-def]
    import numpy as np

    t = np.arange(int(seconds * SR)) / SR
    f = _hz(pitch)
    tone = sum(
        (1 / k) * np.sin(2 * np.pi * k * f * t + phase * k)
        for k in range(1, harmonics + 1)
        if k * f < SR / 2
    )
    attack = np.minimum(1.0, t / 0.005)
    release = np.minimum(1.0, (seconds - t) / 0.01)
    return tone * np.exp(-t / decay) * attack * release


def _add(track, start_s: float, sound) -> None:  # type: ignore[no-untyped-def]
    i = int(start_s * SR)
    track[i : i + len(sound)] += sound[: len(track) - i]


def _synthesize(path: Path) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """Write the stereo stem; return ground truth (onset, pitch) for chords and melody."""
    import numpy as np

    bars = len(CHORD_BARS)
    total = int((bars * 4 * BEAT_S + 1.0) * SR)
    left, right, centre = np.zeros(total), np.zeros(total), np.zeros(total)
    chords: list[tuple[float, int]] = []
    for bar in CHORD_BARS:
        root = CHORD_ROOTS[bar % len(CHORD_ROOTS)]
        for k in range(8):
            t = bar * 4 * BEAT_S + k * EIGHTH_S
            for p in (root, root + 7, root + 12):
                chords.append((t, p))
                _double_take(left, right, t, p, EIGHTH_S)
    melody: list[tuple[float, int]] = []
    for bar, beat, length, p in MELODY:
        t = (bar * 4 + beat) * BEAT_S
        melody.append((t, p))
        _add(centre, t, 0.35 * _pluck(p, length * BEAT_S, 3, 0.6, 0.0))
    _write_stereo(path, left + centre, right + centre)
    return chords, melody


def _write_stereo(path: Path, left, right) -> None:  # type: ignore[no-untyped-def]
    import numpy as np

    stereo = np.stack([left, right], axis=1)
    stereo /= max(1.0, float(np.max(np.abs(stereo))) / 0.9)
    pcm = (stereo * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _double_take(left, right, t: float, pitch: int, seconds: float) -> None:  # type: ignore[no-untyped-def]
    """Two rhythm takes: the right one 10 ms late, 7 cents sharp, other phases."""
    _add(left, t, 0.12 * _pluck(pitch, seconds, 6, 0.15, 0.0))
    _add(right, t + 0.01, 0.12 * _pluck(pitch + 0.07, seconds, 6, 0.15, 1.7))


def _matches(note: NoteEvent, truth: list[tuple[float, int]]) -> bool:
    return any(p == note.pitch and abs(t - note.onset_s) <= ONSET_TOLERANCE_S for t, p in truth)


def _tally(
    notes: list[NoteEvent], roles: Sequence[str], keep: Callable[[NoteEvent], bool]
) -> dict[str, int]:
    counts = {"lead": 0, "rhythm": 0, "both": 0}
    for n, r in zip(notes, roles, strict=True):
        if keep(n):
            counts[r] += 1
    return counts


def _median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def test_synthetic_mix_stem_splits_chords_to_rhythm_and_melody_to_lead(tmp_path: Path) -> None:
    from tabforge_score import Score

    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber
    from tabforge_worker.adapters.librosa_beats import LibrosaBeatTracker
    from tabforge_worker.adapters.stereo import StereoSideAnalyzer
    from tabforge_worker.arrange.split import assign_roles, note_features, stereo_usable
    from tabforge_worker.arrange.tracks import arrange_lead_rhythm

    stem = tmp_path / "guitar.wav"
    chords, melody = _synthesize(stem)
    notes = BasicPitchOnnxTranscriber().transcribe(stem)
    beats = LibrosaBeatTracker().beats(stem)
    ratios = StereoSideAnalyzer().side_ratios(stem, notes)
    assert ratios is not None
    features = note_features(notes, ratios)
    assert stereo_usable(features)
    roles = assign_roles(notes, features, beats)
    # Role rules alone (as for a mono stem), for comparison.
    mono_roles = assign_roles(notes, note_features(notes, None), beats)

    def is_chord(n: NoteEvent) -> bool:
        return _matches(n, chords)

    def is_melody(n: NoteEvent) -> bool:
        return _matches(n, melody)

    def is_other(n: NoteEvent) -> bool:
        return not is_chord(n) and not is_melody(n)

    chord_roles, melody_roles = _tally(notes, roles, is_chord), _tally(notes, roles, is_melody)
    mono_chord, mono_melody = (
        _tally(notes, mono_roles, is_chord),
        _tally(notes, mono_roles, is_melody),
    )
    other_roles = _tally(notes, roles, is_other)
    chord_found, melody_found = sum(chord_roles.values()), sum(melody_roles.values())
    side_of = dict(zip(notes, ratios, strict=True))
    print(  # reported numbers, see docs/eval/M3-lead-rhythm.md
        f"\ntranscribed={len(notes)} chord notes found={chord_found}/{len(chords)} "
        f"melody notes found={melody_found}/{len(melody)} other={sum(other_roles.values())}\n"
        f"chord roles={chord_roles} melody roles={melody_roles} other roles={other_roles}\n"
        f"without stereo: chord roles={mono_chord} melody roles={mono_melody}\n"
        f"side ratio median: chords={_median([side_of[n] for n in notes if is_chord(n)]):.3f} "
        f"melody={_median([side_of[n] for n in notes if is_melody(n)]):.3f}"
    )

    assert chord_found >= 0.5 * len(chords)
    assert melody_found >= 0.8 * len(melody)
    # "Most" = at least 80% in the right track (Rhythm holds rhythm + both, Lead lead + both),
    # and at least 70% only there.
    assert chord_roles["rhythm"] + chord_roles["both"] >= 0.8 * chord_found
    assert melody_roles["lead"] + melody_roles["both"] >= 0.8 * melody_found
    assert chord_roles["rhythm"] >= 0.7 * chord_found
    assert melody_roles["lead"] >= 0.7 * melody_found
    # Without the side feature the role rules alone still put most notes in the right track.
    assert mono_chord["rhythm"] + mono_chord["both"] >= 0.8 * chord_found
    assert mono_melody["lead"] + mono_melody["both"] >= 0.8 * melody_found

    score = Score.model_validate(
        arrange_lead_rhythm(notes, beats, ratios, STANDARD).model_dump(mode="json")
    )
    lead, rhythm = score.track_list()
    assert (score.schema_version, lead.name, rhythm.name) == (3, "Lead", "Rhythm")
    assert len(lead.bars) == len(rhythm.bars)


def test_synthetic_unison_riff_goes_to_both_tracks(tmp_path: Path) -> None:
    import numpy as np

    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber
    from tabforge_worker.adapters.librosa_beats import LibrosaBeatTracker
    from tabforge_worker.adapters.stereo import StereoSideAnalyzer
    from tabforge_worker.arrange.split import assign_roles, note_features

    # A low single-note riff played by the doubled rhythm takes (L/R) and the lead (centre).
    total = int((len(UNISON_RIFF) * EIGHTH_S + 1.0) * SR)
    left, right, centre = np.zeros(total), np.zeros(total), np.zeros(total)
    truth = []
    for k, p in enumerate(UNISON_RIFF):
        t = k * EIGHTH_S
        truth.append((t, p))
        _double_take(left, right, t, p, EIGHTH_S)
        _add(centre, t + 0.005, 0.15 * _pluck(p - 0.05, EIGHTH_S, 6, 0.3, 0.6))
    stem = tmp_path / "guitar.wav"
    _write_stereo(stem, left + centre, right + centre)

    notes = BasicPitchOnnxTranscriber().transcribe(stem)
    beats = LibrosaBeatTracker().beats(stem)
    ratios = StereoSideAnalyzer().side_ratios(stem, notes)
    assert ratios is not None
    roles = assign_roles(notes, note_features(notes, ratios), beats)

    def in_riff(n: NoteEvent) -> bool:
        return _matches(n, truth)

    counts = _tally(notes, roles, in_riff)
    found = sum(counts.values())
    side = _median([r for n, r in zip(notes, ratios, strict=True) if in_riff(n)])
    print(  # reported numbers, see docs/eval/M3-lead-rhythm.md
        f"\nunison: transcribed={len(notes)} riff notes found={found}/{len(truth)} "
        f"roles={counts} side ratio median={side:.3f}"
    )
    assert found >= 0.5 * len(truth)
    assert counts["both"] >= 0.8 * found
