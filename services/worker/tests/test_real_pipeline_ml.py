"""Real models end to end (ml extra): synthetic E4 then A4 -> Score v2 with those pitches."""

import shutil
import uuid
from pathlib import Path

import pytest
from tabforge_score import Score
from test_basic_pitch_onnx import A4_HZ, E4_HZ, _write_tone_sequence

from tabforge_worker.queue import ClaimedJob

pytestmark = [
    pytest.mark.ml,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed"),
]


class ToneSource:
    def download(self, key: str, dst: Path) -> None:
        _write_tone_sequence(dst, [(E4_HZ, 0.5, 1.5), (A4_HZ, 2.0, 3.0)])


def test_real_pipeline_transcribes_synthetic_clip() -> None:
    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber
    from tabforge_worker.adapters.librosa_beats import LibrosaBeatTracker
    from tabforge_worker.real_pipeline import RealPipeline

    def no_separator() -> None:
        raise AssertionError("guitar_stem must not load Demucs")

    pipe = RealPipeline(
        source=ToneSource(),
        transcriber=BasicPitchOnnxTranscriber,
        separator=no_separator,  # type: ignore[arg-type]
        beat_tracker=LibrosaBeatTracker,
    )
    job = ClaimedJob(uuid.uuid4(), uuid.uuid4(), 1, "guitar_stem", uuid.uuid4(), "k", "audio/wav")
    result = pipe.process(job, lambda _: None)

    score = Score.model_validate(result.score)
    attacks = [
        score.tuning[n.string - 1] + n.fret
        for bar in score.bars
        for beat in bar.beats
        for n in beat.notes
        if not n.tie
    ]
    assert attacks == [64, 69]
    assert result.duration_ms == pytest.approx(3500, abs=20)
