"""Guess the guitar's tuning from the transcribed notes (ADR-0013).

The lowest note a guitar plays often is its open low string, so the "floor" of the music (the
pitch with `MIN_FLOOR_NOTES`, or `FLOOR_SHARE` of the notes, at or below it) picks the closest
tuning that reaches it: E, Eb, D, C#, C or B standard, or a drop tuning. A few stray low
notes (bass bleed, octave errors) stay under that count and do not move the tuning; notes
below A1, which no six-string tuning here reaches, are not guitar and are ignored.

A standard tuning and its drop tuning share the low string (D standard and Drop D both reach
D2), so the pitches alone cannot tell them apart: the one where the Viterbi plays the music
with clearly less effort (`DROP_MARGIN` cheaper, notes it cannot place counted heavily) wins,
and the standard tuning on a tie.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from tabforge_worker.arrange.fretting import DEFAULT_WEIGHTS, Weights, path_cost, prepare_events
from tabforge_worker.ports import NoteEvent

STANDARD = (64, 59, 55, 50, 45, 40)  # string 1 (high E) first

CHORD_WINDOW_S = 0.03  # notes starting this close form one chord
MIN_FLOOR_NOTES = 12
FLOOR_SHARE = 0.04  # GuitarSet: 1 false alarm in 240 transcribed E standard recordings
LOWEST_PITCH = 33  # A1, the low string of Drop A
DROP_MARGIN = 0.05
UNPLACED_COST = 10.0  # per note the Viterbi has to leave out


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    tuning: tuple[int, ...]


def _standard(name: str, shift: int) -> Candidate:
    return Candidate(name, tuple(t + shift for t in STANDARD))


def _drop(name: str, shift: int) -> Candidate:
    """`shift` standard with the low string a whole tone lower."""
    base = _standard(name, shift).tuning
    return Candidate(name, (*base[:5], base[5] - 2))


CANDIDATES: tuple[Candidate, ...] = (
    _standard("E standard", 0),
    _standard("Eb standard", -1),
    _standard("D standard", -2),
    _drop("Drop D", 0),
    _standard("C# standard", -3),
    _drop("Drop C#", -1),
    _standard("C standard", -4),
    _drop("Drop C", -2),
    _standard("B standard", -5),
    _drop("Drop B", -3),
    _drop("Drop A", -5),
)


@dataclass(frozen=True, slots=True)
class TuningGuess:
    name: str
    tuning: tuple[int, ...]
    floor: int | None  # the low-note floor it was chosen from; None without enough notes


def _events(notes: Sequence[NoteEvent]) -> list[tuple[list[int], list[int]]]:
    events: list[tuple[list[int], list[int]]] = []
    start: float | None = None
    for note in sorted(notes, key=lambda n: (n.onset_s, n.pitch)):
        if start is None or note.onset_s - start > CHORD_WINDOW_S:
            events.append(([], []))
            start = note.onset_s
        events[-1][0].append(note.pitch)
        events[-1][1].append(note.velocity)
    return events


def _effort(
    events: Sequence[tuple[list[int], list[int]]], tuning: tuple[int, ...], weights: Weights
) -> float:
    prepared = prepare_events(events, tuning)
    unplaced = sum(len(d) for d in prepared.dropped)
    return path_cost(prepared, weights) + UNPLACED_COST * unplaced


def detect_tuning(notes: Sequence[NoteEvent], weights: Weights = DEFAULT_WEIGHTS) -> TuningGuess:
    """The likeliest of `CANDIDATES` for these notes; E standard without enough evidence."""
    guitar = [n for n in notes if n.pitch >= LOWEST_PITCH]
    need = max(MIN_FLOOR_NOTES, math.ceil(FLOOR_SHARE * len(guitar)))
    if len(guitar) < need:
        return TuningGuess(CANDIDATES[0].name, CANDIDATES[0].tuning, None)
    floor = sorted(n.pitch for n in guitar)[need - 1]
    lowest = max(c.tuning[5] for c in CANDIDATES if c.tuning[5] <= floor)
    options = [c for c in CANDIDATES if c.tuning[5] == lowest]  # standard first, then drop
    best = options[0]
    if len(options) > 1:
        events = _events(guitar)
        standard = _effort(events, options[0].tuning, weights)
        for other in options[1:]:
            if _effort(events, other.tuning, weights) < (1 - DROP_MARGIN) * standard:
                best = other
    return TuningGuess(best.name, best.tuning, floor)
