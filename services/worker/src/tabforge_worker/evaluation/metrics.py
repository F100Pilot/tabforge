"""Note-level transcription metrics, wrapping `mir_eval.transcription`."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Protocol

import mir_eval
import numpy as np

ONSET_TOLERANCE_S = 0.05
PITCH_TOLERANCE_CENTS = 50.0
OFFSET_RATIO = 0.2  # mir_eval default: offset within 20% of ref duration (min 50 ms)


class TimedPitch(Protocol):
    @property
    def onset_s(self) -> float: ...
    @property
    def offset_s(self) -> float: ...
    @property
    def pitch(self) -> int: ...


@dataclass(frozen=True, slots=True)
class NoteScores:
    precision: float
    recall: float
    f1: float
    precision_with_offset: float
    recall_with_offset: float
    f1_with_offset: float
    n_ref: int
    n_est: int


def midi_to_hz(pitch: float) -> float:
    return float(440.0 * 2.0 ** ((pitch - 69) / 12))


def score_notes(ref: Sequence[TimedPitch], est: Sequence[TimedPitch]) -> NoteScores:
    """Precision/recall/F1 with onset ±50 ms and pitch ±50 cents, without and with offset."""
    ref_iv, ref_hz = _arrays(ref)
    est_iv, est_hz = _arrays(est)

    def prf(offset_ratio: float | None) -> tuple[float, float, float]:
        p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
            ref_iv,
            ref_hz,
            est_iv,
            est_hz,
            onset_tolerance=ONSET_TOLERANCE_S,
            pitch_tolerance=PITCH_TOLERANCE_CENTS,
            offset_ratio=offset_ratio,
        )
        return float(p), float(r), float(f)

    onset = prf(None)
    with_offset = prf(OFFSET_RATIO)
    return NoteScores(*onset, *with_offset, n_ref=len(ref), n_est=len(est))


def mean_scores(scores: Sequence[NoteScores]) -> NoteScores:
    """Macro average over tracks (each track weighs equally); note counts are summed."""
    if not scores:
        raise ValueError("no scores to average")
    return NoteScores(
        precision=fmean(s.precision for s in scores),
        recall=fmean(s.recall for s in scores),
        f1=fmean(s.f1 for s in scores),
        precision_with_offset=fmean(s.precision_with_offset for s in scores),
        recall_with_offset=fmean(s.recall_with_offset for s in scores),
        f1_with_offset=fmean(s.f1_with_offset for s in scores),
        n_ref=sum(s.n_ref for s in scores),
        n_est=sum(s.n_est for s in scores),
    )


def _arrays(notes: Sequence[TimedPitch]) -> tuple[np.ndarray, np.ndarray]:
    intervals = np.array([(n.onset_s, n.offset_s) for n in notes], dtype=float).reshape(-1, 2)
    hz = np.array([midi_to_hz(n.pitch) for n in notes], dtype=float)
    return intervals, hz
