"""Rhythmic quantization: transcribed notes + beat times -> events on a tick grid.

Decisions (ADR-0002, M0 results):
- Onsets snap to a grid of 12 ticks per beat, which holds both sixteenths (3 ticks) and
  eighth-note triplets (4 ticks). A beat uses triplets only when they fit its onsets clearly
  better than sixteenths.
- Durations come from the next onset (legato), not from Basic Pitch offsets (offset F1 was
  0.55 in M0). Offsets are only used to detect rests of one beat or more.
- Bar 1 starts at the beat at or before the first onset; there is no downbeat detection, and
  the meter is 4/4.
"""

import bisect
import itertools
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from tabforge_worker.ports import NoteEvent

TICKS_PER_BEAT = 12
BEATS_PER_BAR = 4
TICKS_PER_BAR = TICKS_PER_BEAT * BEATS_PER_BAR
SIXTEENTH = 3
TRIPLET_EIGHTH = 4
DEFAULT_BEAT_S = 0.5  # 120 bpm when the beat tracker finds nothing usable
# A beat switches to triplets only if they cut the snapping error by more than half.
TRIPLET_ADVANTAGE = 0.5


@dataclass(frozen=True, slots=True)
class Event:
    """Notes struck together, from tick `start` until tick `end` (exclusive)."""

    start: int
    end: int
    pitches: tuple[int, ...]
    velocities: tuple[int, ...] = field(default=(), compare=False)


@dataclass(frozen=True, slots=True)
class Quantized:
    events: tuple[Event, ...]
    triplet_beats: frozenset[int]
    total_ticks: int
    tempo_bpm: int


class _Grid:
    def __init__(self, beats: Sequence[float], first: float, last: float) -> None:
        clean = sorted({b for b in beats if b >= 0})
        diffs = [b - a for a, b in itertools.pairwise(clean) if b > a]
        self.period = statistics.median(diffs) if diffs else DEFAULT_BEAT_S
        times = clean if len(clean) >= 2 else [first]
        while times[0] > first + 1e-9:
            times.insert(0, times[0] - self.period)
        while len(times) > 1 and times[1] <= first + 1e-9:
            times.pop(0)
        while times[-1] < last + self.period:
            times.append(times[-1] + self.period)
        self.times = times

    def locate(self, t: float) -> tuple[int, float]:
        """Beat index containing `t` and the position inside it (0..1)."""
        i = max(0, min(bisect.bisect_right(self.times, t) - 1, len(self.times) - 2))
        start, end = self.times[i], self.times[i + 1]
        return i, max(0.0, (t - start) / (end - start))


def _snap_error(fracs: list[float], divisions: int) -> float:
    return sum(abs(f - round(f * divisions) / divisions) for f in fracs)


def quantize(notes: Sequence[NoteEvent], beats: Sequence[float]) -> Quantized:
    """Place notes on the tick grid. `beats` are beat times in seconds (any order)."""
    if not notes:
        return Quantized((), frozenset(), TICKS_PER_BAR, _tempo(DEFAULT_BEAT_S))

    first = min(n.onset_s for n in notes)
    last = max(n.offset_s for n in notes)
    grid = _Grid(beats, first, last)

    by_beat: dict[int, list[float]] = {}
    for n in notes:
        i, f = grid.locate(n.onset_s)
        by_beat.setdefault(i, []).append(f)
    triplets = frozenset(
        i
        for i, fracs in by_beat.items()
        if len(fracs) >= 2 and _snap_error(fracs, 3) < TRIPLET_ADVANTAGE * _snap_error(fracs, 4)
    )

    def snap(t: float) -> int:
        i, f = grid.locate(t)
        if i in triplets:
            return i * TICKS_PER_BEAT + round(f * 3) * TRIPLET_EIGHTH
        return i * TICKS_PER_BEAT + round(f * 4) * SIXTEENTH

    def step(tick: int) -> int:
        return TRIPLET_EIGHTH if tick // TICKS_PER_BEAT in triplets else SIXTEENTH

    grouped: dict[int, dict[int, tuple[int, int]]] = {}  # start -> pitch -> (velocity, off)
    for n in notes:
        start = snap(n.onset_s)
        off = snap(n.offset_s)
        slot = grouped.setdefault(start, {})
        velocity, previous_off = slot.get(n.pitch, (0, 0))
        slot[n.pitch] = (max(velocity, n.velocity), max(previous_off, off))

    starts = sorted(grouped)
    events: list[Event] = []
    for index, start in enumerate(starts):
        slot = grouped[start]
        off = max(max(o for _, o in slot.values()), start + step(start))
        if index + 1 < len(starts):
            nxt = starts[index + 1]
            end = off if off <= nxt - TICKS_PER_BEAT else nxt
        else:
            end = off
        pitches = tuple(sorted(slot))
        events.append(Event(start, end, pitches, tuple(slot[p][0] for p in pitches)))

    total = max(TICKS_PER_BAR, math.ceil(events[-1].end / TICKS_PER_BAR) * TICKS_PER_BAR)
    return Quantized(tuple(events), triplets, total, _tempo(grid.period))


def _tempo(beat_s: float) -> int:
    return max(20, min(400, round(60 / beat_s)))
