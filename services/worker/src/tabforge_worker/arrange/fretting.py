"""String/fret assignment by dynamic programming (Viterbi) over the note events.

Cost of a path = sum over events of a hand-shape cost (chord span, fret height) plus a
transition cost (how far the fretting hand moves). Open strings do not fix the hand, so
moves to or from an all-open shape are cheaper. Strings are numbered 1 (highest) .. 6.

Notes that cannot be placed are removed and reported (US-02): pitches outside the
fretboard as `out_of_range`; notes that cannot share the strings with the rest of a chord as
`too_many_notes`, quietest first.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

MAX_FRET = 24
MAX_SPAN = 4  # frets between lowest and highest fretted note of a chord
RELAXED_SPAN = 7  # tried when no shape fits MAX_SPAN


@dataclass(frozen=True, slots=True)
class Weights:
    """Chosen on GuitarSet players 00-02 (best train accuracy among weights that keep an open
    E-to-D scale in first position), checked on players 03-05: 0.657 exact vs 0.625 before.
    See docs/eval/M2-arranging.md."""

    span: float = 1.0
    height: float = 0.05
    move: float = 0.5
    open_move: float = 0.25


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True, slots=True)
class Position:
    string: int
    fret: int


@dataclass(frozen=True, slots=True)
class Fretted:
    pitches: tuple[int, ...]
    positions: tuple[Position, ...]
    dropped: tuple[tuple[int, str], ...] = ()


Shape = tuple[Position, ...]


def candidate_positions(pitch: int, tuning: Sequence[int]) -> list[Position]:
    """Every (string, fret) that sounds `pitch`, string 1 first."""
    return [
        Position(string, pitch - open_pitch)
        for string, open_pitch in enumerate(tuning, 1)
        if 0 <= pitch - open_pitch <= MAX_FRET
    ]


def _shapes(pitches: Sequence[int], tuning: Sequence[int], max_span: int) -> list[Shape]:
    options = [candidate_positions(p, tuning) for p in pitches]
    found: list[Shape] = []

    def walk(i: int, chosen: list[Position], used: set[int]) -> None:
        if i == len(options):
            fretted = [p.fret for p in chosen if p.fret > 0]
            if not fretted or max(fretted) - min(fretted) <= max_span:
                found.append(tuple(chosen))
            return
        for pos in options[i]:
            if pos.string not in used:
                chosen.append(pos)
                used.add(pos.string)
                walk(i + 1, chosen, used)
                used.discard(pos.string)
                chosen.pop()

    walk(0, [], set())
    return found


def _playable(
    pitches: Sequence[int], velocities: Sequence[int], tuning: Sequence[int]
) -> tuple[list[int], list[Shape], list[tuple[int, str]]]:
    dropped: list[tuple[int, str]] = []
    vel = list(velocities) if len(velocities) == len(pitches) else [0] * len(pitches)
    keep: list[tuple[int, int]] = []
    for pitch, velocity in zip(pitches, vel, strict=True):
        if candidate_positions(pitch, tuning):
            keep.append((pitch, velocity))
        else:
            dropped.append((pitch, "out_of_range"))
    while keep:
        shapes = []
        if len(keep) <= len(tuning):
            kept = [p for p, _ in keep]
            shapes = _shapes(kept, tuning, MAX_SPAN) or _shapes(kept, tuning, RELAXED_SPAN)
        if shapes:
            return [p for p, _ in keep], shapes, dropped
        quietest = min(range(len(keep)), key=lambda i: (keep[i][1], -keep[i][0]))
        dropped.append((keep.pop(quietest)[0], "too_many_notes"))
    return [], [()], dropped


def _center(shape: Shape) -> float | None:
    fretted = [p.fret for p in shape if p.fret > 0]
    return fmean(fretted) if fretted else None


def _shape_cost(shape: Shape, w: Weights) -> float:
    fretted = [p.fret for p in shape if p.fret > 0]
    if not fretted:
        return 0.0
    return w.span * (max(fretted) - min(fretted)) + w.height * fmean(fretted)


def _move_cost(a: Shape, b: Shape, w: Weights) -> float:
    ca, cb = _center(a), _center(b)
    if ca is not None and cb is not None:
        return w.move * abs(ca - cb)
    return w.open_move * abs((ca or 0.0) - (cb or 0.0))


def assign_positions(
    events: Sequence[tuple[Sequence[int], Sequence[int]]],
    tuning: Sequence[int],
    weights: Weights = DEFAULT_WEIGHTS,
) -> list[Fretted]:
    """Choose a (string, fret) for every note. `events` = (pitches, velocities) per event."""
    if not events:
        return []
    prepared = [_playable(p, v, tuning) for p, v in events]

    costs = [_shape_cost(s, weights) for s in prepared[0][1]]
    back: list[list[int]] = []
    for i in range(1, len(prepared)):
        prev_shapes, shapes = prepared[i - 1][1], prepared[i][1]
        new_costs, pointers = [], []
        for shape in shapes:
            best = min(
                range(len(prev_shapes)),
                key=lambda j: costs[j] + _move_cost(prev_shapes[j], shape, weights),
            )
            new_costs.append(
                costs[best]
                + _move_cost(prev_shapes[best], shape, weights)
                + _shape_cost(shape, weights)
            )
            pointers.append(best)
        costs = new_costs
        back.append(pointers)

    choice = min(range(len(costs)), key=costs.__getitem__)
    chosen = [choice]
    for pointers in reversed(back):
        choice = pointers[choice]
        chosen.append(choice)
    chosen.reverse()

    return [
        Fretted(tuple(kept), shapes[k], tuple(dropped))
        for (kept, shapes, dropped), k in zip(prepared, chosen, strict=True)
    ]
