"""Split the notes of a mixed guitar stem into Lead and Rhythm (ADR-0010, "Guitarra com banda").

Demucs gives one guitar stem with both guitars in it, so the split is made on the transcribed
notes, with explainable rules (no model):

1. Features per note (`note_features`): how much of its energy is in the stereo "side" channel
   (measured from the audio by `adapters.stereo`), how many notes form a chord shape with it,
   its pitch, how often the same low pitch repeats nearby, and its duration.
2. A score per note (`note_score`): positive leans Rhythm, negative leans Lead.
   - Doubled rhythm guitars panned left and right put a lot of energy in the side channel; the
     lead tends to sit in the centre.
   - Chord shapes (power chords, open chords) are Rhythm.
   - A single note at or above E4 is Lead; low notes, more so repeated ones, are Rhythm.
3. Smoothing (`assign_roles`): each note takes the average score of the notes around it, in
   time (its half-bar on the beat grid and the two next to it) and in register (within a
   fifth), so one odd note does not flip the role of a line. Notes struck together as one chord
   shape share their role.
4. When that average is close to zero (|score| < BOTH_MARGIN) the note goes to both tracks (user
   decision for passages where both guitars play the same riff). A riff in unison, with the lead
   in the centre and the rhythm takes at the sides, has a side ratio in between (UNISON_*) and
   scores 0 on purpose.

When the stem is mono, or both channels are nearly identical everywhere, the side feature says
nothing and is left out (`stereo_usable`); the other rules still apply.

All weights and thresholds below are first guesses checked only on synthetic audio
(docs/eval/M3-lead-rhythm.md); they are to be tuned against the user's reference tabs.
"""

import bisect
import itertools
import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tabforge_worker.ports import NoteEvent

Role = Literal["lead", "rhythm", "both"]

# --- Features -----------------------------------------------------------------------------------
# Notes whose onsets are this close are struck together (the M0/M2 chord tolerance is 30-50 ms).
ONSET_WINDOW_S = 0.05
# Notes struck together belong to one chord shape while the gap between neighbouring pitches is
# at most a fifth (open and barre chords stack fourths, thirds and fifths). A lead note more than
# a fifth above the top of a chord is a separate voice, not part of that chord.
CHORD_GAP = 7
# A low note "repeats" when the same pitch is struck again within this many seconds...
REPEAT_WINDOW_S = 1.0
# ...at least this many other times (e.g. a chugged E2 riff).
REPEAT_MIN = 2

# --- Score: positive -> Rhythm, negative -> Lead ----------------------------------------------
# Side ratio (side energy / (mid + side) energy, 0 = centred, 0.5 = hard-panned or decorrelated
# doubled takes) mapped linearly to -1..+1: SIDE_NEUTRAL gives 0, SIDE_NEUTRAL +/- SIDE_SPAN
# gives +/-1. Reverb and Demucs bleed put some side energy even on a centred guitar, hence the
# neutral point above zero.
SIDE_NEUTRAL = 0.2
SIDE_SPAN = 0.2
W_SIDE = 1.0
# Two or more notes in one chord shape: accompaniment.
W_CHORD = 1.0
# A single note at or above E4 (first string open): melody / solo register.
LEAD_PITCH = 64
W_HIGH = 1.0
# Below G3 (the open third string), i.e. the register of riffs on the three low strings.
LOW_PITCH = 55
W_LOW = 0.5
# Extra for a low pitch that repeats (REPEAT_MIN times within REPEAT_WINDOW_S).
W_REPEAT = 0.5
# Duration is recorded but not scored: Basic Pitch offsets are unreliable (offset F1 0.55 in M0).
# Unison: a centred lead and doubled rhythm takes playing the same riff give a side ratio in
# between (equal power per take: 0.25; lead 3x louder: 0.14; lead half as loud: 0.33). A single
# note below LEAD_PITCH in this band counts as no evidence (score 0), so the riff goes to both
# tracks (user decision). Known false positive: one guitar panned part-way (e.g. 70% left) also
# falls in this band and is then copied to both tracks.
UNISON_LOW = 0.12
UNISON_HIGH = 0.32

# --- Smoothing and decision ---------------------------------------------------------------------
BEATS_PER_SEGMENT = 2  # half a bar of 4/4
NEIGHBOUR_SEGMENT_WEIGHT = 0.5  # the half-bars before and after count half as much as the own one
SMOOTH_PITCH_RANGE = 7  # only notes within a fifth take part in a note's average
BOTH_MARGIN = 0.35  # |average score| below this -> the note goes to both tracks
DEFAULT_BEAT_S = 0.5  # beat length when the tracker found fewer than two beats (as quantize)

# --- Stereo usability -------------------------------------------------------------------------
# The side feature is used only if at least the top decile of notes has this much side energy;
# below it, the two channels are (nearly) the same everywhere and the feature carries no signal.
STEREO_MIN_SPREAD = 0.05
STEREO_PERCENTILE = 0.9


@dataclass(frozen=True, slots=True)
class NoteFeatures:
    side_ratio: float | None  # None: mono stem or no stereo analysis
    polyphony: int  # notes in this note's chord shape, itself included
    pitch: int
    duration_s: float
    repeats: int  # other onsets of the same pitch within REPEAT_WINDOW_S


def shape_groups(notes: Sequence[NoteEvent]) -> list[int]:
    """A group id per note: notes struck together (ONSET_WINDOW_S) that stack within CHORD_GAP."""
    order = sorted(range(len(notes)), key=lambda i: (notes[i].onset_s, notes[i].pitch))
    groups = [0] * len(notes)
    next_id = 0
    k = 0
    while k < len(order):
        start = notes[order[k]].onset_s
        cluster = [order[k]]
        k += 1
        while k < len(order) and notes[order[k]].onset_s - start <= ONSET_WINDOW_S:
            cluster.append(order[k])
            k += 1
        cluster.sort(key=lambda i: notes[i].pitch)
        previous: int | None = None
        for i in cluster:
            if previous is not None and notes[i].pitch - notes[previous].pitch > CHORD_GAP:
                next_id += 1
            groups[i] = next_id
            previous = i
        next_id += 1
    return groups


def note_features(
    notes: Sequence[NoteEvent], side_ratios: Sequence[float] | None
) -> list[NoteFeatures]:
    """Features of each note; `side_ratios` (one per note) come from the stereo stem, or None."""
    if side_ratios is not None and len(side_ratios) != len(notes):
        raise ValueError("need one side ratio per note")
    groups = shape_groups(notes)
    sizes: dict[int, int] = defaultdict(int)
    for g in groups:
        sizes[g] += 1
    onsets_by_pitch: dict[int, list[float]] = defaultdict(list)
    for n in notes:
        onsets_by_pitch[n.pitch].append(n.onset_s)
    for onsets in onsets_by_pitch.values():
        onsets.sort()

    features = []
    for i, n in enumerate(notes):
        onsets = onsets_by_pitch[n.pitch]
        near = bisect.bisect_right(onsets, n.onset_s + REPEAT_WINDOW_S) - bisect.bisect_left(
            onsets, n.onset_s - REPEAT_WINDOW_S
        )
        features.append(
            NoteFeatures(
                side_ratio=None if side_ratios is None else float(side_ratios[i]),
                polyphony=sizes[groups[i]],
                pitch=n.pitch,
                duration_s=n.offset_s - n.onset_s,
                repeats=near - 1,
            )
        )
    return features


def stereo_usable(features: Sequence[NoteFeatures]) -> bool:
    """False when the stem is mono or its channels are nearly identical for (almost) every note."""
    ratios = sorted(f.side_ratio for f in features if f.side_ratio is not None)
    if not ratios:
        return False
    return ratios[math.floor(STEREO_PERCENTILE * (len(ratios) - 1))] >= STEREO_MIN_SPREAD


def note_score(f: NoteFeatures, use_side: bool) -> float:
    """Evidence for Rhythm (> 0) or Lead (< 0) from one note's own features."""
    score = 0.0
    if use_side and f.side_ratio is not None:
        if f.polyphony == 1 and f.pitch < LEAD_PITCH and UNISON_LOW <= f.side_ratio <= UNISON_HIGH:
            return 0.0
        score += W_SIDE * max(-1.0, min(1.0, (f.side_ratio - SIDE_NEUTRAL) / SIDE_SPAN))
    if f.polyphony >= 2:
        score += W_CHORD
    elif f.pitch >= LEAD_PITCH:
        score -= W_HIGH
    if f.pitch < LOW_PITCH:
        score += W_LOW
        if f.repeats >= REPEAT_MIN:
            score += W_REPEAT
    return score


class _BeatClock:
    """Beat position (in beats, fractional) of a time, extrapolated outside the tracked beats."""

    def __init__(self, beats: Sequence[float]) -> None:
        self.times = sorted({b for b in beats if b >= 0})
        diffs = [b - a for a, b in itertools.pairwise(self.times)]
        self.period = statistics.median(diffs) if diffs else DEFAULT_BEAT_S
        if len(self.times) < 2:
            self.times = [0.0]

    def position(self, t: float) -> float:
        times = self.times
        i = bisect.bisect_right(times, t) - 1
        if i < 0:
            return (t - times[0]) / self.period
        if i >= len(times) - 1:
            return (len(times) - 1) + (t - times[-1]) / self.period
        return i + (t - times[i]) / (times[i + 1] - times[i])

    def segment(self, t: float) -> int:
        return math.floor(self.position(t) / BEATS_PER_SEGMENT)


def assign_roles(
    notes: Sequence[NoteEvent], features: Sequence[NoteFeatures], beats: Sequence[float]
) -> list[Role]:
    """Lead / Rhythm / both for each note (see the module docstring for the rules)."""
    if len(features) != len(notes):
        raise ValueError("need one NoteFeatures per note")
    use_side = stereo_usable(features)
    raw = [note_score(f, use_side) for f in features]
    clock = _BeatClock(beats)
    segments = [clock.segment(n.onset_s) for n in notes]
    by_segment: dict[int, list[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        by_segment[seg].append(i)

    smoothed = []
    for i, n in enumerate(notes):
        total = weight = 0.0
        for seg, w in (
            (segments[i] - 1, NEIGHBOUR_SEGMENT_WEIGHT),
            (segments[i], 1.0),
            (segments[i] + 1, NEIGHBOUR_SEGMENT_WEIGHT),
        ):
            for j in by_segment.get(seg, ()):
                if abs(notes[j].pitch - n.pitch) <= SMOOTH_PITCH_RANGE:
                    total += w * raw[j]
                    weight += w
        smoothed.append(total / weight)  # weight > 0: the note itself always counts

    groups = shape_groups(notes)
    members: dict[int, list[float]] = defaultdict(list)
    for g, s in zip(groups, smoothed, strict=True):
        members[g].append(s)
    decided: dict[int, Role] = {g: _decide(statistics.fmean(s)) for g, s in members.items()}
    return [decided[g] for g in groups]


def _decide(score: float) -> Role:
    if score >= BOTH_MARGIN:
        return "rhythm"
    if score <= -BOTH_MARGIN:
        return "lead"
    return "both"


def split_notes(
    notes: Sequence[NoteEvent], roles: Sequence[Role]
) -> tuple[list[NoteEvent], list[NoteEvent]]:
    """(lead notes, rhythm notes); a note with role "both" is in both lists."""
    if len(roles) != len(notes):
        raise ValueError("need one role per note")
    lead = [n for n, r in zip(notes, roles, strict=True) if r in ("lead", "both")]
    rhythm = [n for n, r in zip(notes, roles, strict=True) if r in ("rhythm", "both")]
    return lead, rhythm
