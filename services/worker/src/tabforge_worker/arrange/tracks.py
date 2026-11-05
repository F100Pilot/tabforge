"""Transcribed notes + beats -> Score: one guitar (v2) or Lead and Rhythm tracks (v3, ADR-0010).

Each track goes through the same quantize -> fretting -> layout chain. The Lead and Rhythm tracks
are quantized on one grid (same bar 1, tempo and beat grid) and padded with rests to the same
number of bars. A track with no notes is all rests; the Score warning codes are only for notes
that could not be placed, so an empty track is not reported as a warning.
"""

from collections.abc import Sequence
from dataclasses import replace

from tabforge_score import Score

from tabforge_worker.arrange.fretting import DEFAULT_WEIGHTS, Fretted, Weights, assign_positions
from tabforge_worker.arrange.layout import build_score, build_tracks_score
from tabforge_worker.arrange.quantize import Quantized, quantize
from tabforge_worker.arrange.split import assign_roles, note_features, split_notes
from tabforge_worker.ports import NoteEvent

LEAD_TRACK = "Lead"
RHYTHM_TRACK = "Rhythm"


def _fret(quantized: Quantized, tuning: Sequence[int], weights: Weights) -> list[Fretted]:
    return assign_positions([(e.pitches, e.velocities) for e in quantized.events], tuning, weights)


def arrange_guitar(
    notes: Sequence[NoteEvent],
    beats: Sequence[float],
    tuning: Sequence[int],
    weights: Weights = DEFAULT_WEIGHTS,
) -> Score:
    """One guitar (isolated stem): Score v2. `weights`: the owner's tuned ones (ADR-0011)."""
    quantized = quantize(notes, beats)
    return build_score(quantized, _fret(quantized, tuning, weights), tuning)


def arrange_lead_rhythm(
    notes: Sequence[NoteEvent],
    beats: Sequence[float],
    side_ratios: Sequence[float] | None,
    tuning: Sequence[int],
    weights: Weights = DEFAULT_WEIGHTS,
) -> Score:
    """Guitar stem of a band mix: Score v3 with tracks "Lead" and "Rhythm" (see arrange.split)."""
    roles = assign_roles(notes, note_features(notes, side_ratios), beats)
    lead, rhythm = split_notes(notes, roles)
    span = (min(n.onset_s for n in notes), max(n.offset_s for n in notes)) if notes else None
    parts = [
        (LEAD_TRACK, quantize(lead, beats, span)),
        (RHYTHM_TRACK, quantize(rhythm, beats, span)),
    ]
    total = max(q.total_ticks for _, q in parts)
    padded = [(name, replace(q, total_ticks=total)) for name, q in parts]
    return build_tracks_score([(name, q, _fret(q, tuning, weights)) for name, q in padded], tuning)
