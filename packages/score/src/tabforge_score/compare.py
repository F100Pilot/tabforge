"""Compare a transcribed tab with the correct tab of the same song (M3, ADR-0009).

Both sides are reduced to note events: onset in quarter notes from the start, MIDI pitch, and the
string/fret that plays it (string 1 = high E). Time is measured in beats, not seconds, so the two
tabs can have different tempos. The correct tab may also start earlier or later (an intro, a
count-in) and the transcription may have locked onto double or half tempo, so `compare` first
searches for the shift and the scale that line most notes up, then matches notes one to one.

Repeats in the correct tab are not expanded: a section written once with a repeat sign is
compared once.
"""

import bisect
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from tabforge_score.model import Score, beat_value

TOLERANCE = 0.25  # quarter notes: a sixteenth either way counts as the same attack
MAX_SHIFT = 256.0  # quarter notes (64 bars of 4/4) of intro or offset
SCALES = (1.0, 0.5, 2.0)  # transcription at the same, double or half tempo
CANDIDATES = 5  # best-voted shifts tried per scale


@dataclass(frozen=True, slots=True)
class NoteEvent:
    onset: float | Fraction  # quarter notes from the start
    pitch: int
    string: int
    fret: int
    bar: int = 1


@dataclass(frozen=True, slots=True)
class BarResult:
    bar: int  # 1-based, in the correct tab
    reference_notes: int
    matched: int
    positions_ok: int


@dataclass(frozen=True, slots=True)
class Comparison:
    shift: float  # quarter notes added to the transcription's onsets (after scaling)
    scale: float
    matched: int
    ai_notes: int
    reference_notes: int
    recall: float  # share of the correct notes that the transcription found
    precision: float  # share of the transcribed notes that are in the correct tab
    f1: float
    position_accuracy: float | None  # matched notes on the same string and fret
    onset_error: float | None  # mean |onset difference| of matched notes, quarter notes
    bars: tuple[BarResult, ...]


def score_events(score: Score) -> list[NoteEvent]:
    """Attacked notes of a Score (tie continuations are not new notes)."""
    events: list[NoteEvent] = []
    position = Fraction(0)  # whole notes
    for index, bar in enumerate(score.bars, 1):
        for beat in bar.beats:
            for note in beat.notes:
                if not note.tie:
                    events.append(
                        NoteEvent(
                            onset=position * 4,
                            pitch=score.tuning[note.string - 1] + note.fret,
                            string=note.string,
                            fret=note.fret,
                            bar=index,
                        )
                    )
            position += beat_value(beat)
    return events


def _by_pitch(events: Iterable[NoteEvent]) -> dict[int, list[float]]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for event in events:
        grouped[event.pitch].append(float(event.onset))
    return grouped


def _candidate_shifts(
    ai: Sequence[NoteEvent], ref: Sequence[NoteEvent], scale: float, tolerance: float
) -> list[float]:
    """Shifts voted for by same-pitch pairs, best first (0 is always tried)."""
    ai_onsets, ref_onsets = _by_pitch(ai), _by_pitch(ref)
    votes: Counter[int] = Counter()
    for pitch, refs in ref_onsets.items():
        for a in ai_onsets.get(pitch, ()):
            for r in refs:
                delta = r - scale * a
                if abs(delta) <= MAX_SHIFT:
                    votes[round(delta / tolerance)] += 1
    keys = [key for key, _ in votes.most_common(CANDIDATES)]
    return [0.0, *(key * tolerance for key in keys if key != 0)]


def _match(
    ai: Sequence[NoteEvent],
    ref: Sequence[NoteEvent],
    scale: float,
    shift: float,
    tolerance: float,
) -> list[tuple[NoteEvent, NoteEvent, float]]:
    """Greedy one-to-one matching in reference order: nearest unused same-pitch attack."""
    pools: dict[int, tuple[list[float], list[int]]] = {}
    for pitch in {e.pitch for e in ai}:
        indexed = sorted(
            (scale * float(e.onset) + shift, i) for i, e in enumerate(ai) if e.pitch == pitch
        )
        pools[pitch] = ([t for t, _ in indexed], [i for _, i in indexed])
    used: set[int] = set()
    pairs: list[tuple[NoteEvent, NoteEvent, float]] = []
    for r in sorted(ref, key=lambda e: float(e.onset)):
        pool = pools.get(r.pitch)
        if pool is None:
            continue
        times, indices = pool
        target = float(r.onset)
        best: tuple[float, int] | None = None
        start = bisect.bisect_left(times, target - tolerance)
        for k in range(start, len(times)):
            if times[k] > target + tolerance:
                break
            if indices[k] in used:
                continue
            error = abs(times[k] - target)
            if best is None or error < best[0]:
                best = (error, indices[k])
        if best is not None:
            used.add(best[1])
            pairs.append((ai[best[1]], r, best[0]))
    return pairs


def compare(
    ai: Sequence[NoteEvent],
    reference: Sequence[NoteEvent],
    *,
    tolerance: float = TOLERANCE,
    shifts: bool = True,
) -> Comparison:
    """Best alignment of `ai` onto `reference`, then recall/precision/positions per bar.

    shifts=False compares as given (no shift or tempo search), e.g. for an edited revision.
    """
    best: tuple[tuple[int, float, float], float, float, list[tuple[NoteEvent, NoteEvent, float]]]
    best = ((-1, 0.0, 0.0), 0.0, 1.0, [])
    for scale in SCALES if shifts else (1.0,):
        candidates = _candidate_shifts(ai, reference, scale, tolerance) if shifts else [0.0]
        for shift in candidates:
            pairs = _match(ai, reference, scale, shift, tolerance)
            # Most matches; then the plainest alignment (scale 1, small shift).
            rank = (len(pairs), -float(scale != 1.0), -abs(shift))
            if rank > best[0]:
                best = (rank, shift, scale, pairs)
    _, shift, scale, pairs = best

    matched = len(pairs)
    recall = matched / len(reference) if reference else 0.0
    precision = matched / len(ai) if ai else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    positions_ok = sum(1 for a, r, _ in pairs if (a.string, a.fret) == (r.string, r.fret))

    per_bar: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in reference:
        per_bar[r.bar][0] += 1
    for a, r, _ in pairs:
        per_bar[r.bar][1] += 1
        per_bar[r.bar][2] += int((a.string, a.fret) == (r.string, r.fret))

    return Comparison(
        shift=shift,
        scale=scale,
        matched=matched,
        ai_notes=len(ai),
        reference_notes=len(reference),
        recall=recall,
        precision=precision,
        f1=f1,
        position_accuracy=positions_ok / matched if matched else None,
        onset_error=sum(e for _, _, e in pairs) / matched if matched else None,
        bars=tuple(BarResult(bar, *counts) for bar, counts in sorted(per_bar.items())),
    )
