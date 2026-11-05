"""Learn a player's string/fret choices from their correct tabs (ADR-0011). Pure; no database.

Training data, one set of notes per tab: the notes of its correct tab (every track with a
reference), or else the notes of its latest user-edited revision when they differ from the AI's.
Notes with the same onset form one event (a chord). The Viterbi (`arrange.fretting`) runs again
on the pitches of those events, and the measure is the share of notes placed on exactly the
correct string and fret.

`tune` grid-searches the four `Weights`. With 3 or more tabs the result is judged by leave-one-
tab-out cross-validation: each tab is placed with the weights that do best on the other tabs, and
the weights are accepted only if those held-out placements beat the default weights. With 2 tabs
the comparison is in-sample. Below `MIN_NOTES` notes or `MIN_TABS` tabs nothing is tuned.
"""

import logging
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from itertools import product
from typing import Any, Literal

from tabforge_score import Score
from tabforge_score.compare import NoteEvent, score_events

from tabforge_worker.arrange.fretting import (
    DEFAULT_WEIGHTS,
    Position,
    Weights,
    best_path,
    prepare_events,
)

log = logging.getLogger("tabforge_worker")

MIN_NOTES = 200
MIN_TABS = 2
CV_MIN_TABS = 3
MAX_TRAINING_NOTES = 5_000  # whole tabs, newest first; bounds a refresh to a few seconds
STANDARD_TUNING = (64, 59, 55, 50, 45, 40)  # string 1 (high E) first
VELOCITY = 90  # correct tabs have no dynamics; equal velocities for every note

# 7 x 5 x 5 = 175 combinations around the M2 weights (docs/eval/M2-arranging.md). Only the ratios
# between the weights change the Viterbi path, so `span` stays at 1. A negative height rewards
# higher frets, for players who prefer to play up the neck.
GRID_HEIGHT = (-0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.4)
GRID_MOVE = (0.1, 0.25, 0.5, 1.0, 2.0)
GRID_OPEN_MOVE = (0.0, 0.1, 0.25, 0.5, 1.0)
GRID: tuple[Weights, ...] = tuple(
    Weights(1.0, height, move, open_move)
    for height, move, open_move in product(GRID_HEIGHT, GRID_MOVE, GRID_OPEN_MOVE)
)


@dataclass(frozen=True, slots=True)
class TrainingEvent:
    pitches: tuple[int, ...]  # ascending, as the quantizer gives them
    positions: tuple[Position, ...]  # the correct (string, fret) of each note


@dataclass(frozen=True, slots=True)
class TrainingTrack:
    """One track of one tab. Cross-validation holds out all tracks of a tab together."""

    tab: str
    tuning: tuple[int, ...]
    events: tuple[TrainingEvent, ...]

    @property
    def notes(self) -> int:
        return sum(len(e.positions) for e in self.events)


@dataclass(frozen=True, slots=True)
class ReferenceRow:
    """A stored reference (tab_references.notes) and the tuning of the tab's track, if known."""

    tab: str
    track_index: int
    notes: Sequence[Any]
    tuning: Any


@dataclass(frozen=True, slots=True)
class RevisionRow:
    """A tab without reference: its latest user revision and its first AI revision (scores)."""

    tab: str
    edited: Any
    generated: Any


@dataclass(frozen=True, slots=True)
class Choice:
    index: int  # into the candidates; 0 is the default weights
    accepted: bool
    default_accuracy: float
    tuned_accuracy: float  # cross-validated when cross_validate, else in-sample


@dataclass(frozen=True, slots=True)
class TuningResult:
    status: Literal["ready", "insufficient"]
    weights: Weights | None  # accepted weights, better than the default; else None
    default_accuracy: float | None
    tuned_accuracy: float | None
    tabs: int
    notes: int


def group_events(notes: Iterable[NoteEvent]) -> tuple[TrainingEvent, ...]:
    """Notes with the same onset are one event; events in time order, pitches ascending."""
    by_onset: dict[float, list[NoteEvent]] = defaultdict(list)
    for note in notes:
        by_onset[round(float(note.onset), 6)].append(note)
    events = []
    for onset in sorted(by_onset):
        chord = sorted(by_onset[onset], key=lambda n: (n.pitch, n.string))
        events.append(
            TrainingEvent(
                tuple(n.pitch for n in chord), tuple(Position(n.string, n.fret) for n in chord)
            )
        )
    return tuple(events)


def infer_tuning(notes: Iterable[NoteEvent], fallback: Sequence[int]) -> tuple[int, ...]:
    """Open-string pitches as the notes play them (pitch - fret), string by string.

    A correct tab can be in another tuning than the tab it is compared with (drop D...); strings
    without notes keep `fallback`.
    """
    seen: dict[int, Counter[int]] = defaultdict(Counter)
    for note in notes:
        seen[note.string][note.pitch - note.fret] += 1
    return tuple(
        seen[string].most_common(1)[0][0] if seen[string] else open_pitch
        for string, open_pitch in enumerate(fallback, 1)
    )


def _tuning_hint(value: Any) -> tuple[int, ...]:
    if (
        isinstance(value, list)
        and len(value) == len(STANDARD_TUNING)
        and all(isinstance(v, int) for v in value)
    ):
        return tuple(value)
    return STANDARD_TUNING


def _reference_track(row: ReferenceRow) -> TrainingTrack:
    notes = [NoteEvent(**n) for n in row.notes]
    tuning = infer_tuning(notes, _tuning_hint(row.tuning))
    return TrainingTrack(row.tab, tuning, group_events(notes))


def _score_tracks(score: Score) -> list[tuple[tuple[int, ...], list[NoteEvent]]]:
    return [
        (tuple(track.tuning), score_events(score, index))
        for index, track in enumerate(score.track_list())
    ]


def _revision_tracks(row: RevisionRow) -> list[TrainingTrack]:
    if row.edited is None:
        return []
    edited = _score_tracks(Score.model_validate(row.edited))
    if row.generated is not None and edited == _score_tracks(Score.model_validate(row.generated)):
        return []  # saved without changing a note
    return [
        TrainingTrack(row.tab, tuning, group_events(notes)) for tuning, notes in edited if notes
    ]


def build_training_set(
    references: Sequence[ReferenceRow],
    revisions: Sequence[RevisionRow],
    max_notes: int = MAX_TRAINING_NOTES,
) -> list[TrainingTrack]:
    """Tracks to learn from, in the order given (newest tabs first), whole tabs up to `max_notes`.

    A tab with a reference learns only from it. Unreadable rows are skipped.
    """
    by_tab: dict[str, list[TrainingTrack]] = {}
    for reference in references:
        try:
            track = _reference_track(reference)
        except (TypeError, ValueError, KeyError, IndexError):
            log.warning('{"event": "training_row_skipped", "tab": "%s"}', reference.tab)
            continue
        if track.events:
            by_tab.setdefault(reference.tab, []).append(track)
    for revision in revisions:
        if revision.tab in by_tab:
            continue
        try:
            tracks = _revision_tracks(revision)
        except (TypeError, ValueError, KeyError, IndexError):
            log.warning('{"event": "training_row_skipped", "tab": "%s"}', revision.tab)
            continue
        if tracks:
            by_tab[revision.tab] = tracks
    kept: list[TrainingTrack] = []
    total = 0
    for tracks in by_tab.values():
        size = sum(t.notes for t in tracks)
        if total + size <= max_notes:
            kept.extend(tracks)
            total += size
    return kept


def _best(counts: Sequence[int]) -> int:
    """Index of the highest count; the first (the default) on ties."""
    return max(range(len(counts)), key=lambda i: (counts[i], -i))


def choose(counts: Sequence[Sequence[int]], notes: int, cross_validate: bool) -> Choice:
    """Pick weights from `counts[tab][candidate]` (correct notes); candidate 0 is the default.

    Cross-validated: each tab counts with the candidate that is best on the other tabs. The
    result is accepted only if it beats the default and is not the default itself.
    """
    totals = [sum(column) for column in zip(*counts, strict=True)]
    best = _best(totals)
    default_accuracy = totals[0] / notes
    if cross_validate:
        held_out = 0
        for tab_counts in counts:
            rest = [total - own for total, own in zip(totals, tab_counts, strict=True)]
            held_out += tab_counts[_best(rest)]
        tuned_accuracy = held_out / notes
    else:
        tuned_accuracy = totals[best] / notes
    accepted = best != 0 and tuned_accuracy > default_accuracy
    return Choice(best, accepted, default_accuracy, tuned_accuracy)


def _correct_per_tab(
    tracks: Sequence[TrainingTrack], candidates: Sequence[Weights]
) -> dict[str, list[int]]:
    """Correct notes of every tab with every candidate (one shape preparation per track)."""
    counts: dict[str, list[int]] = {}
    for track in tracks:
        prepared = prepare_events(
            [(e.pitches, (VELOCITY,) * len(e.pitches)) for e in track.events], track.tuning
        )
        # Correct notes of each candidate shape of each event (a multiset match).
        hits = [
            [sum((Counter(shape) & Counter(event.positions)).values()) for shape in shapes]
            for event, shapes in zip(track.events, prepared.shapes, strict=True)
        ]
        tab_counts = counts.setdefault(track.tab, [0] * len(candidates))
        for c, weights in enumerate(candidates):
            path = best_path(prepared, weights)
            tab_counts[c] += sum(row[k] for row, k in zip(hits, path, strict=True))
    return counts


def tune(
    tracks: Sequence[TrainingTrack],
    grid: Sequence[Weights] = GRID,
    default: Weights = DEFAULT_WEIGHTS,
) -> TuningResult:
    """Grid-search the weights on `tracks` (see the module docstring)."""
    tabs = len({t.tab for t in tracks if t.events})
    notes = sum(t.notes for t in tracks)
    if notes == 0:
        return TuningResult("insufficient", None, None, None, tabs, 0)
    if notes < MIN_NOTES or tabs < MIN_TABS:
        default_count = sum(c[0] for c in _correct_per_tab(tracks, [default]).values())
        return TuningResult("insufficient", None, default_count / notes, None, tabs, notes)
    candidates = list(dict.fromkeys([default, *grid]))
    counts = _correct_per_tab(tracks, candidates)
    choice = choose(list(counts.values()), notes, cross_validate=tabs >= CV_MIN_TABS)
    return TuningResult(
        "ready",
        candidates[choice.index] if choice.accepted else None,
        choice.default_accuracy,
        choice.tuned_accuracy,
        tabs,
        notes,
    )


_WEIGHT_FIELDS = tuple(f.name for f in fields(Weights))


def weights_to_json(weights: Weights) -> dict[str, float]:
    return {name: float(getattr(weights, name)) for name in _WEIGHT_FIELDS}


def weights_from_json(value: Any) -> Weights | None:
    """Stored weights ({span, height, move, open_move}), or None if absent or malformed."""
    if not isinstance(value, dict) or set(value) != set(_WEIGHT_FIELDS):
        return None
    if not all(
        isinstance(value[n], int | float) and not isinstance(value[n], bool) for n in _WEIGHT_FIELDS
    ):
        return None
    return Weights(**{n: float(value[n]) for n in _WEIGHT_FIELDS})
