"""String/fret assignment by dynamic programming (Viterbi) over the note events (ADR-0016:
shared by the worker, which frets new transcriptions, and the API, which re-frets tabs).

Cost of a path = sum over events of a hand-shape cost (chord span, fret height) plus a
transition cost (how far the fretting hand moves). Open strings do not fix the hand, so
moves to or from an all-open shape are cheaper. Strings are numbered 1 (highest) .. 6.

Notes that cannot be placed are removed and reported (US-02): pitches outside the
fretboard as `out_of_range`; notes that cannot share the strings with the rest of a chord as
`too_many_notes`, quietest first.
"""

from collections.abc import Mapping, Sequence
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


Moves = tuple[tuple[float, ...], tuple[float, ...]]


@dataclass(frozen=True, slots=True)
class PreparedEvents:
    """The playable shapes of every event and their costs' terms, computed once for any number
    of `Weights` (the weight search in `learning` reruns the Viterbi hundreds of times).

    `spreads[i][k]`/`centers[i][k]`: fret span and mean fret of the fretted notes of
    `shapes[i][k]` (center None for an all-open or empty shape). `moves[i][k]` (i >= 1): the
    center change from each shape of event i - 1, split in two tuples: changes between fretted
    shapes (0 where a shape is all open) and changes to or from an all-open shape (0 elsewhere).
    """

    pitches: tuple[tuple[int, ...], ...]
    shapes: tuple[tuple[Shape, ...], ...]
    dropped: tuple[tuple[tuple[int, str], ...], ...]
    spreads: tuple[tuple[int, ...], ...]
    centers: tuple[tuple[float | None, ...], ...]
    moves: tuple[tuple[Moves, ...], ...]


def _moves(previous: Sequence[float | None], current: Sequence[float | None]) -> tuple[Moves, ...]:
    out = []
    for cb in current:
        fretted, open_ = [], []
        for ca in previous:
            if ca is not None and cb is not None:
                fretted.append(abs(ca - cb))
                open_.append(0.0)
            else:
                fretted.append(0.0)
                open_.append(abs((ca or 0.0) - (cb or 0.0)))
        out.append((tuple(fretted), tuple(open_)))
    return tuple(out)


def prepare_events(
    events: Sequence[tuple[Sequence[int], Sequence[int]]],
    tuning: Sequence[int],
    fixed: Mapping[int, Shape] | None = None,
) -> PreparedEvents:
    """Drop unplayable notes and list the shapes of each event (see `assign_positions`).

    `fixed` gives some events (by index) their only shape: the positions of their pitches, in
    the same order. The path then has to pass through them (re-fretting keeps them, ADR-0016).
    """
    prepared = [
        (list(p), [fixed[i]], []) if fixed is not None and i in fixed else _playable(p, v, tuning)
        for i, (p, v) in enumerate(events)
    ]
    spreads: list[tuple[int, ...]] = []
    centers: list[tuple[float | None, ...]] = []
    for _, shapes, _ in prepared:
        spread_row: list[int] = []
        for shape in shapes:
            fretted = [p.fret for p in shape if p.fret > 0]
            spread_row.append(max(fretted) - min(fretted) if fretted else 0)
        spreads.append(tuple(spread_row))
        centers.append(tuple(_center(shape) for shape in shapes))
    moves = [()] + [_moves(centers[i - 1], centers[i]) for i in range(1, len(centers))]
    return PreparedEvents(
        pitches=tuple(tuple(kept) for kept, _, _ in prepared),
        shapes=tuple(tuple(shapes) for _, shapes, _ in prepared),
        dropped=tuple(tuple(dropped) for _, _, dropped in prepared),
        spreads=tuple(spreads),
        centers=tuple(centers),
        moves=tuple(moves),
    )


def _viterbi(prepared: PreparedEvents, weights: Weights) -> tuple[list[float], list[list[int]]]:
    """Cheapest cost of ending on each shape of the last event, and the back pointers."""
    w_span, w_height, w_move, w_open = weights.span, weights.height, weights.move, weights.open_move

    costs = [
        0.0 if center is None else w_span * spread + w_height * center
        for spread, center in zip(prepared.spreads[0], prepared.centers[0], strict=True)
    ]
    back: list[list[int]] = []
    for i in range(1, len(prepared.shapes)):
        new_costs: list[float] = []
        pointers: list[int] = []
        for (fretted, open_), spread, center in zip(
            prepared.moves[i], prepared.spreads[i], prepared.centers[i], strict=True
        ):
            # One of the two terms is always 0, so this is exactly cost + one move cost.
            totals = [
                c + (w_move * f + w_open * o) for c, f, o in zip(costs, fretted, open_, strict=True)
            ]
            best_total = min(totals)
            pointers.append(totals.index(best_total))
            new_costs.append(
                best_total + (0.0 if center is None else w_span * spread + w_height * center)
            )
        costs = new_costs
        back.append(pointers)
    return costs, back


def best_path(prepared: PreparedEvents, weights: Weights = DEFAULT_WEIGHTS) -> list[int]:
    """Viterbi: the index of the chosen shape of every event (cheapest path, first on ties).

    Hand-shape cost: span * fret spread + height * mean fret (0 for an all-open shape).
    Move cost: move * |center change|, or open_move * |change| when either shape is all open.
    """
    if not prepared.shapes:
        return []
    costs, back = _viterbi(prepared, weights)
    choice = min(range(len(costs)), key=costs.__getitem__)
    chosen = [choice]
    for pointers in reversed(back):
        choice = pointers[choice]
        chosen.append(choice)
    chosen.reverse()
    return chosen


def path_cost(prepared: PreparedEvents, weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Total cost of the cheapest path (`best_path`): how hard the music is to play."""
    return min(_viterbi(prepared, weights)[0]) if prepared.shapes else 0.0


def assign_positions(
    events: Sequence[tuple[Sequence[int], Sequence[int]]],
    tuning: Sequence[int],
    weights: Weights = DEFAULT_WEIGHTS,
) -> list[Fretted]:
    """Choose a (string, fret) for every note. `events` = (pitches, velocities) per event."""
    prepared = prepare_events(events, tuning)
    return [
        Fretted(kept, shapes[k], dropped)
        for kept, shapes, dropped, k in zip(
            prepared.pitches,
            prepared.shapes,
            prepared.dropped,
            best_path(prepared, weights),
            strict=True,
        )
    ]
