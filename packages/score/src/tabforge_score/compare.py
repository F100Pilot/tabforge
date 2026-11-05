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
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Literal

from tabforge_score.model import MAX_FRET, STRING_COUNT, Score, beat_value

TOLERANCE = 0.25  # quarter notes: a sixteenth either way counts as the same attack
MAX_SHIFT = 256.0  # quarter notes (64 bars of 4/4) of intro or offset
SCALES = (1.0, 0.5, 2.0)  # transcription at the same, double or half tempo
CANDIDATES = 5  # best-voted shifts tried per scale
TIMING_TOLERANCE = 0.125  # quarter notes: a matched attack further off is a timing difference


@dataclass(frozen=True, slots=True)
class NoteEvent:
    onset: float | Fraction  # quarter notes from the start
    pitch: int
    string: int
    fret: int
    bar: int = 1
    beat_index: int | None = field(
        default=None, compare=False
    )  # 0-based beat within its bar (AI side; None for references)


@dataclass(frozen=True, slots=True)
class BarResult:
    bar: int  # 1-based, in the correct tab
    reference_notes: int
    matched: int
    positions_ok: int


DifferenceKind = Literal["position", "missing", "extra", "timing"]


@dataclass(frozen=True, slots=True)
class Difference:
    kind: DifferenceKind
    bar: int  # bar in the correct tab (for "extra": the transcription's own bar)
    onset: float  # correct-tab timeline, quarter notes ("extra": AI onset scaled and shifted)
    pitch: int
    ai_string: int | None
    ai_fret: int | None
    ref_string: int | None
    ref_fret: int | None
    onset_error: float | None  # |AI onset - reference onset| of matched notes
    ai_bar: int | None
    ai_beat: int | None  # 0-based beat index inside ai_bar


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
    differences: tuple[Difference, ...] = ()


def score_events(score: Score, track: int = 0) -> list[NoteEvent]:
    """Attacked notes of one track of a Score (tie continuations are not new notes).

    `track` indexes `score.track_list()` (a v1/v2 score has only track 0); a track that does not
    exist, negative indices included, raises IndexError.
    """
    tracks = score.track_list()
    if not 0 <= track < len(tracks):
        raise IndexError(f"track {track} does not exist, the score has {len(tracks)}")
    chosen = tracks[track]
    events: list[NoteEvent] = []
    position = Fraction(0)  # whole notes
    for index, bar in enumerate(chosen.bars, 1):
        for beat_index, beat in enumerate(bar.beats):
            for note in beat.notes:
                if not note.tie:
                    events.append(
                        NoteEvent(
                            onset=position * 4,
                            pitch=chosen.tuning[note.string - 1] + note.fret,
                            string=note.string,
                            fret=note.fret,
                            bar=index,
                            beat_index=beat_index,
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


def _differences(
    ai: Sequence[NoteEvent],
    reference: Sequence[NoteEvent],
    pairs: list[tuple[NoteEvent, NoteEvent, float]],
    scale: float,
    shift: float,
) -> tuple[Difference, ...]:
    found: list[Difference] = []
    matched_ai = {id(a) for a, _, _ in pairs}
    matched_ref = {id(r) for _, r, _ in pairs}
    for a, r, error in pairs:
        same_position = (a.string, a.fret) == (r.string, r.fret)
        if same_position and error <= TIMING_TOLERANCE:
            continue
        found.append(
            Difference(
                kind="timing" if same_position else "position",
                bar=r.bar,
                onset=float(r.onset),
                pitch=r.pitch,
                ai_string=a.string,
                ai_fret=a.fret,
                ref_string=r.string,
                ref_fret=r.fret,
                onset_error=error,
                ai_bar=a.bar,
                ai_beat=a.beat_index,
            )
        )
    for r in reference:
        if id(r) not in matched_ref:
            found.append(
                Difference(
                    "missing",
                    r.bar,
                    float(r.onset),
                    r.pitch,
                    None,
                    None,
                    r.string,
                    r.fret,
                    None,
                    None,
                    None,
                )
            )
    for a in ai:
        if id(a) not in matched_ai:
            found.append(
                Difference(
                    "extra",
                    a.bar,
                    scale * float(a.onset) + shift,
                    a.pitch,
                    a.string,
                    a.fret,
                    None,
                    None,
                    None,
                    a.bar,
                    a.beat_index,
                )
            )
    found.sort(key=lambda d: d.onset)  # stable: ties keep position/timing, missing, extra order
    return tuple(found)


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
        differences=_differences(ai, reference, pairs, scale, shift),
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


Cell = tuple[int, int]  # (flat beat index, string)


def corrected_score(
    score: Score,
    track: int,
    reference: Sequence[NoteEvent],
    *,
    comparison: Comparison | None = None,
) -> tuple[Score, int, int]:
    """Set the strings and frets of `track` to the reference's wherever a matched note differs.

    A note and its tie continuations (same string, following beats with tie=True) form a chain
    that moves as one. All corrections are applied together, so chord notes can swap or rotate
    strings. A note the correct tab does not have ("extra") that holds a target string is moved
    to the nearest free string with the same pitch. A correction is skipped when the target
    string stays taken (a correct note, a tie held from an earlier note, or another correction),
    when the fret is out of range, or when the reference position would sound a different pitch
    in the track's tuning. Other tracks are untouched. Returns (new score, applied, skipped).
    """
    events = score_events(score, track)  # also validates the track index
    result = comparison or compare(events, reference)
    tuning = score.track_list()[track].tuning
    data: dict[str, Any] = score.model_dump(mode="json")
    bars: list[dict[str, Any]] = (
        data["tracks"][track]["bars"] if score.schema_version == 3 else data["bars"]
    )
    flat = [(b, i) for b, bar in enumerate(bars) for i in range(len(bar["beats"]))]
    where = {pos: n for n, pos in enumerate(flat)}

    # Every chain, keyed by the cell of its attack: its notes and the beats it spans.
    chains: dict[Cell, list[dict[str, Any]]] = {}
    span: dict[Cell, range] = {}
    open_chain: dict[int, Cell] = {}  # string -> chain that the next tie on it continues
    for n, (b, i) in enumerate(flat):
        on_beat: dict[int, Cell] = {}
        for note in bars[b]["beats"][i]["notes"]:
            string = note["string"]
            key = open_chain.get(string) if note["tie"] else None
            if key is None:
                key = (n, string)
                chains[key] = []
            chains[key].append(note)
            span[key] = range(key[0], n + 1)
            on_beat[string] = key
        open_chain = on_beat

    # Valid corrections: chain -> (target string, fret).
    moves: dict[Cell, tuple[int, int]] = {}
    skipped = 0
    for diff in result.differences:
        if diff.kind != "position":
            continue
        start = (
            None
            if diff.ai_bar is None or diff.ai_beat is None
            else where.get((diff.ai_bar - 1, diff.ai_beat))
        )
        key = None if start is None or diff.ai_string is None else (start, diff.ai_string)
        chain = None if key is None else chains.get(key)
        target, fret = diff.ref_string, diff.ref_fret
        if (
            key is None
            or not chain
            or chain[0]["tie"]
            or chain[0]["fret"] != diff.ai_fret
            or target is None
            or fret is None
            or not 1 <= target <= STRING_COUNT
            or not 0 <= fret <= MAX_FRET
            or tuning[target - 1] + fret != diff.pitch
            or key in moves
        ):
            skipped += 1
            continue
        moves[key] = (target, fret)

    extras = {
        (where[(d.ai_bar - 1, d.ai_beat)], d.ai_string)
        for d in result.differences
        if d.kind == "extra"
        and d.ai_bar is not None
        and d.ai_beat is not None
        and d.ai_string is not None
        and (d.ai_bar - 1, d.ai_beat) in where
    }
    relocated: dict[Cell, tuple[int, int]] = {}  # extra chain -> (string, fret) out of the way

    def string_of(key: Cell) -> int:
        if key in moves:
            return moves[key][0]
        if key in relocated:
            return relocated[key][0]
        return key[1]

    def claims() -> dict[Cell, list[Cell]]:
        cells: dict[Cell, list[Cell]] = defaultdict(list)
        for key, beats in span.items():
            string = string_of(key)
            for n in beats:
                cells[(n, string)].append(key)
        return cells

    def relocate(key: Cell, cells: dict[Cell, list[Cell]]) -> bool:
        pitch = tuning[key[1] - 1] + chains[key][0]["fret"]
        free = [
            s
            for s in range(1, STRING_COUNT + 1)
            if s != key[1]
            and 0 <= pitch - tuning[s - 1] <= MAX_FRET
            and all(not cells.get((n, s)) for n in span[key])
        ]
        if not free:
            return False
        best = min(free, key=lambda s: (abs(s - key[1]), s))
        relocated[key] = (best, pitch - tuning[best - 1])
        return True

    # Resolve clashes until none is left; every round relocates an extra or drops a correction.
    while True:
        cells = claims()
        clash = next((keys for keys in cells.values() if len(keys) > 1), None)
        if clash is None:
            break
        staying = [k for k in clash if k not in moves]
        movable = [k for k in staying if k in extras and k not in relocated]
        if movable and relocate(movable[0], cells):
            continue
        # Drop the correction that started last (a tie from an earlier note keeps its string).
        moved_in = [k for k in clash if k in moves]
        drop = max(moved_in) if moved_in else None
        if drop is None:  # cannot happen: the input itself has no two notes on one cell
            break
        del moves[drop]
        skipped += 1

    for key, (string, fret) in [*moves.items(), *relocated.items()]:
        for note in chains[key]:
            note["string"], note["fret"] = string, fret
    return Score.model_validate(data), len(moves), skipped
