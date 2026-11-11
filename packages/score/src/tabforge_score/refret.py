"""Choose the strings and frets of an existing tab again with other Viterbi weights (ADR-0016).

The pitches, rhythm and ties stay; only (string, fret) change. A note and its tie continuations
(same string, following beats with tie=True) form a chain that moves as one. The Viterbi runs
over the attacked notes of each beat, as when the worker frets a transcription. A continuation
can end up on the string of a note attacked in its beat; then every event with a note sounding
in that beat keeps its original shape, and the path is searched again through those fixed
events, until no beat has two notes on one string (at worst the tab stays as it was). An event
whose chord the Viterbi cannot place (a span wider than it allows) also keeps its shape.
"""

from collections.abc import Sequence
from typing import Any

from tabforge_score.fretting import Position, Shape, Weights, best_path, prepare_events
from tabforge_score.model import Score, ScoreBar

VELOCITY = 90  # the score has no dynamics; every note counts the same when a chord is pruned


class _Chain:
    """One attacked note and its tie continuations: `cells` are (beat, note) in the track."""

    def __init__(self, pitch: int, original: Position) -> None:
        self.pitch = pitch
        self.original = original
        self.position = original  # then the Viterbi's choice
        self.cells: list[tuple[int, int]] = []


def _chains(
    bars: Sequence[ScoreBar], tuning: Sequence[int]
) -> tuple[list[_Chain], list[list[int]]]:
    """Every chain, and the chains attacked in each beat (in track order)."""
    chains: list[_Chain] = []
    attacked: list[list[int]] = []
    sounding: dict[int, int] = {}  # string -> chain at the end of the previous beat
    beat_index = 0
    for bar in bars:
        for beat in bar.beats:
            here: dict[int, int] = {}
            attacks: list[int] = []
            for note_index, note in enumerate(beat.notes):
                if note.tie:
                    chain = sounding[note.string]  # the model guarantees the previous note
                else:
                    chain = len(chains)
                    chains.append(
                        _Chain(
                            tuning[note.string - 1] + note.fret, Position(note.string, note.fret)
                        )
                    )
                    attacks.append(chain)
                chains[chain].cells.append((beat_index, note_index))
                here[note.string] = chain
            sounding = here
            attacked.append(
                sorted(attacks, key=lambda c: (chains[c].pitch, chains[c].original.string))
            )
            beat_index += 1
    return chains, attacked


def _assign(
    chains: list[_Chain],
    events: list[list[int]],
    tuning: Sequence[int],
    weights: Weights,
    fixed: dict[int, Shape],
) -> None:
    prepared = prepare_events(
        [([chains[c].pitch for c in ev], [VELOCITY] * len(ev)) for ev in events], tuning, fixed
    )
    for i, (event, shapes, dropped, k) in enumerate(
        zip(events, prepared.shapes, prepared.dropped, best_path(prepared, weights), strict=True)
    ):
        if dropped and i not in fixed:
            fixed[i] = tuple(chains[c].original for c in event)  # cannot place it: keep it
        for chain, position in zip(event, shapes[k], strict=False):
            chains[chain].position = position


def _track_bars(
    bars: Sequence[ScoreBar], tuning: Sequence[int], weights: Weights
) -> tuple[list[dict[str, Any]], int]:
    chains, attacked = _chains(bars, tuning)
    event_beats = [b for b, attacks in enumerate(attacked) if attacks]
    events = [attacked[b] for b in event_beats]
    event_of = {c: i for i, ev in enumerate(events) for c in ev}
    beat_count = len(attacked)
    fixed: dict[int, Shape] = {}
    while True:
        before = len(fixed)
        _assign(chains, events, tuning, weights, fixed)
        if len(fixed) > before:
            continue  # an event could not be placed: search again with it fixed
        strings: list[dict[int, list[int]]] = [{} for _ in range(beat_count)]
        for index, chain in enumerate(chains):
            for beat, _ in chain.cells:
                strings[beat].setdefault(chain.position.string, []).append(index)
        clashes: set[int] = set()
        for on_string in strings:
            if any(len(owners) > 1 for owners in on_string.values()):
                clashes.update(event_of[c] for owners in on_string.values() for c in owners)
        new = clashes - fixed.keys()
        if not new:
            break
        for i in new:
            fixed[i] = tuple(chains[c].original for c in events[i])

    out = [bar.model_dump() for bar in bars]
    flat = [beat for bar in out for beat in bar["beats"]]
    changed = 0
    for chain in chains:
        if chain.position != chain.original:
            changed += 1
        for beat, note in chain.cells:
            flat[beat]["notes"][note]["string"] = chain.position.string
            flat[beat]["notes"][note]["fret"] = chain.position.fret
    return out, changed


def refretted_score(score: Score, weights: Weights) -> tuple[Score, int]:
    """Every track placed again with `weights`; returns (new score, attacked notes moved)."""
    data = score.model_dump()
    changed = 0
    if score.schema_version == 3:
        for index, track in enumerate(score.tracks):
            data["tracks"][index]["bars"], moved = _track_bars(track.bars, track.tuning, weights)
            changed += moved
    else:
        data["bars"], changed = _track_bars(score.bars, score.tuning, weights)
    if changed == 0:
        return score, 0
    return Score.model_validate(data), changed
