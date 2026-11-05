"""Quantized events + string/fret positions -> Score v2, or v3 with tracks (bars, ties, warnings).

Durations are written with plain or dotted values on a binary grid; a beat marked as triplet is
written as three triplet eighths (notes or rests). A note longer than one value, or crossing a
barline, is split into tied pieces.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tabforge_score import Score

from tabforge_worker.arrange.fretting import Fretted, Position
from tabforge_worker.arrange.quantize import TICKS_PER_BAR, TICKS_PER_BEAT, Quantized

TRIPLET_UNIT = 4  # ticks in one triplet eighth

# (ticks, duration, dots), longest first
_BINARY: tuple[tuple[int, int, int], ...] = (
    (48, 1, 0),
    (36, 2, 1),
    (24, 2, 0),
    (18, 4, 1),
    (12, 4, 0),
    (9, 8, 1),
    (6, 8, 0),
    (3, 16, 0),
)


@dataclass(frozen=True, slots=True)
class Piece:
    ticks: int
    duration: int
    dots: int = 0
    tuplet: int | None = None


def _allowed(ticks: int, pos_in_bar: int) -> bool:
    """Engraving rule of thumb: long values start on beats, short ones stay inside a beat."""
    in_beat = pos_in_bar % TICKS_PER_BEAT
    if ticks == 48:
        return pos_in_bar == 0
    if ticks == 36:
        return in_beat == 0 and pos_in_bar + ticks <= TICKS_PER_BAR
    if ticks == 24:
        return in_beat == 0
    if ticks in (18, 12):
        return pos_in_bar % 6 == 0
    if ticks in (9, 6):
        return pos_in_bar % 3 == 0 and in_beat + ticks <= TICKS_PER_BEAT
    return True


def decompose(start: int, length: int, triplet_beats: frozenset[int]) -> list[Piece]:
    """Split a span (absolute ticks, within one bar) into writable note values."""
    pieces: list[Piece] = []
    pos, end = start, start + length
    while pos < end:
        beat = pos // TICKS_PER_BEAT
        if beat in triplet_beats:
            if pos % TRIPLET_UNIT or end - pos < TRIPLET_UNIT:
                raise ValueError(f"span at tick {pos} is not on the triplet grid")
            pieces.append(Piece(TRIPLET_UNIT, 8, tuplet=3))
            pos += TRIPLET_UNIT
            continue
        limit = min(end, (pos // TICKS_PER_BAR + 1) * TICKS_PER_BAR)
        next_beat = beat + 1
        while next_beat * TICKS_PER_BEAT < limit:
            if next_beat in triplet_beats:
                limit = next_beat * TICKS_PER_BEAT
                break
            next_beat += 1
        remaining = limit - pos
        for ticks, duration, dots in _BINARY:
            if ticks <= remaining and _allowed(ticks, pos % TICKS_PER_BAR):
                pieces.append(Piece(ticks, duration, dots))
                pos += ticks
                break
        else:
            raise ValueError(f"cannot write {remaining} ticks at tick {pos}")
    return pieces


def _track_content(
    quantized: Quantized, fretted: Sequence[Fretted]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(bars, warnings) of one guitar, as Score JSON."""
    if len(fretted) != len(quantized.events):
        raise ValueError("build_score needs one Fretted per event")

    spans: list[tuple[int, int, tuple[Position, ...]]] = []
    cursor = 0
    for event, placed in zip(quantized.events, fretted, strict=True):
        if event.start > cursor:
            spans.append((cursor, event.start, ()))
        spans.append((event.start, event.end, placed.positions))
        cursor = event.end
    if cursor < quantized.total_ticks:
        spans.append((cursor, quantized.total_ticks, ()))

    bars: list[list[dict[str, Any]]] = [[] for _ in range(quantized.total_ticks // TICKS_PER_BAR)]
    for start, end, positions in spans:
        pos = start
        while pos < end:
            chunk_end = min(end, (pos // TICKS_PER_BAR + 1) * TICKS_PER_BAR)
            for piece in decompose(pos, chunk_end - pos, quantized.triplet_beats):
                notes = [
                    {"string": p.string, "fret": p.fret, "tie": pos > start} for p in positions
                ]
                beat: dict[str, Any] = {"duration": piece.duration, "notes": notes}
                if piece.dots:
                    beat["dots"] = piece.dots
                if piece.tuplet:
                    beat["tuplet"] = piece.tuplet
                bars[pos // TICKS_PER_BAR].append(beat)
                pos += piece.ticks

    warnings = [
        {"bar": event.start // TICKS_PER_BAR + 1, "code": code, "pitch": pitch}
        for event, placed in zip(quantized.events, fretted, strict=True)
        for pitch, code in placed.dropped
    ]
    return [{"beats": beats} for beats in bars], warnings


def build_score(quantized: Quantized, fretted: Sequence[Fretted], tuning: Sequence[int]) -> Score:
    """Assemble a validated Score v2. `tuning`: open-string MIDI pitches, string 1 first."""
    bars, warnings = _track_content(quantized, fretted)
    return Score.model_validate(
        {
            "schema_version": 2,
            "tempo_bpm": quantized.tempo_bpm,
            "time_signature": [4, 4],
            "tuning": list(tuning),
            "bars": bars,
            "warnings": warnings,
        }
    )


def build_tracks_score(
    tracks: Sequence[tuple[str, Quantized, Sequence[Fretted]]], tuning: Sequence[int]
) -> Score:
    """Assemble a validated Score v3 (ADR-0010) from (name, quantized, fretted) per track.

    The tracks must share the tempo and the length in ticks (quantize them with the same `span`
    and pad the shorter ones), so that they have the same bars.
    """
    if not tracks:
        raise ValueError("build_tracks_score needs at least one track")
    if (
        len({q.tempo_bpm for _, q, _ in tracks}) > 1
        or len({q.total_ticks for _, q, _ in tracks}) > 1
    ):
        raise ValueError("tracks must share tempo and length")
    content = []
    for name, quantized, fretted in tracks:
        bars, warnings = _track_content(quantized, fretted)
        content.append({"name": name, "tuning": list(tuning), "bars": bars, "warnings": warnings})
    return Score.model_validate(
        {
            "schema_version": 3,
            "tempo_bpm": tracks[0][1].tempo_bpm,
            "time_signature": [4, 4],
            "tracks": content,
        }
    )
