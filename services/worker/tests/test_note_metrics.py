"""Note-level transcription metrics (mir_eval). Requires the `ml` extra."""

import pytest

pytest.importorskip("mir_eval")

from tabforge_worker.evaluation.metrics import (
    NoteScores,
    mean_scores,
    midi_to_hz,
    score_notes,
)
from tabforge_worker.ports import NoteEvent

pytestmark = pytest.mark.ml


def _n(onset: float, offset: float, pitch: int) -> NoteEvent:
    return NoteEvent(onset_s=onset, offset_s=offset, pitch=pitch, velocity=100)


def test_midi_to_hz_a4_is_440() -> None:
    assert midi_to_hz(69) == pytest.approx(440.0)
    assert midi_to_hz(57) == pytest.approx(220.0)


def test_perfect_transcription_scores_one() -> None:
    ref = [_n(0.0, 0.5, 64), _n(0.5, 1.0, 69)]
    scores = score_notes(ref, ref)
    assert (scores.f1, scores.f1_with_offset) == (1.0, 1.0)
    assert (scores.n_ref, scores.n_est) == (2, 2)


def test_onset_within_50ms_matches_beyond_does_not() -> None:
    ref = [_n(1.0, 2.0, 60)]
    assert score_notes(ref, [_n(1.049, 2.0, 60)]).f1 == 1.0
    assert score_notes(ref, [_n(1.051, 2.0, 60)]).f1 == 0.0


def test_wrong_pitch_does_not_match() -> None:
    assert score_notes([_n(0.0, 1.0, 60)], [_n(0.0, 1.0, 61)]).f1 == 0.0


def test_offset_metric_is_stricter_than_onset_only() -> None:
    scores = score_notes([_n(0.0, 1.0, 60)], [_n(0.0, 0.5, 60)])
    assert scores.f1 == 1.0
    assert scores.f1_with_offset == 0.0


def test_precision_and_recall_with_extra_and_missed_notes() -> None:
    ref = [_n(0.0, 0.5, 60), _n(1.0, 1.5, 62)]
    est = [_n(0.0, 0.5, 60), _n(2.0, 2.5, 70), _n(3.0, 3.5, 71)]
    scores = score_notes(ref, est)
    assert scores.precision == pytest.approx(1 / 3)
    assert scores.recall == pytest.approx(1 / 2)
    assert scores.f1 == pytest.approx(0.4)


def test_empty_estimate_scores_zero() -> None:
    scores = score_notes([_n(0.0, 1.0, 60)], [])
    assert (scores.precision, scores.recall, scores.f1) == (0.0, 0.0, 0.0)


def test_mean_scores_averages_per_track_and_sums_counts() -> None:
    a = NoteScores(1.0, 1.0, 1.0, 0.5, 0.5, 0.5, n_ref=10, n_est=10)
    b = NoteScores(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, n_ref=4, n_est=2)
    assert mean_scores([a, b]) == NoteScores(0.5, 0.5, 0.5, 0.25, 0.25, 0.25, n_ref=14, n_est=12)


def test_mean_scores_rejects_empty() -> None:
    with pytest.raises(ValueError):
        mean_scores([])
