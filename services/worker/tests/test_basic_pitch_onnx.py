"""Integration guard for the ADR-0002 dependency overrides.

Runs real Basic Pitch inference on its bundled ONNX model, without TensorFlow, on a
synthetic clip. Fails if the override set (no tensorflow, resampy>=0.4.3) breaks
inference. Requires the `ml` extra: `uv run pytest -m ml`.
"""

import importlib.util
import math
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.ml

SAMPLE_RATE = 22050
ONSET_TOLERANCE_S = 0.05
E4_HZ = 329.63
A4_HZ = 440.0


def _write_tone_sequence(path: Path, tones: list[tuple[float, float, float]]) -> None:
    """Write 16-bit mono WAV with (freq_hz, start_s, end_s) sine tones, 10 ms fades."""
    total_s = max(end for _, _, end in tones) + 0.5
    n = int(total_s * SAMPLE_RATE)
    samples = [0.0] * n
    fade = int(0.01 * SAMPLE_RATE)
    for freq, start, end in tones:
        i0, i1 = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
        for i in range(i0, i1):
            gain = min(1.0, (i - i0) / fade, (i1 - i) / fade)
            samples[i] += 0.5 * gain * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)
    frames = b"".join(
        int(max(-1.0, min(1.0, s)) * 32767).to_bytes(2, "little", signed=True) for s in samples
    )
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)


def test_tensorflow_is_not_installed() -> None:
    assert importlib.util.find_spec("tensorflow") is None


def test_onnx_inference_detects_e4_then_a4(tmp_path: Path) -> None:
    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber

    clip = tmp_path / "e4_a4.wav"
    _write_tone_sequence(clip, [(E4_HZ, 0.5, 1.5), (A4_HZ, 2.0, 3.0)])

    notes = BasicPitchOnnxTranscriber().transcribe(clip)

    assert sorted({n.pitch for n in notes}) == [64, 69]
    first_e4 = min(n.onset_s for n in notes if n.pitch == 64)
    first_a4 = min(n.onset_s for n in notes if n.pitch == 69)
    assert abs(first_e4 - 0.5) <= ONSET_TOLERANCE_S
    assert abs(first_a4 - 2.0) <= ONSET_TOLERANCE_S
