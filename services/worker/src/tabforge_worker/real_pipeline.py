"""The real transcription pipeline: S3 audio -> ffmpeg -> (Demucs) -> Basic Pitch + beats -> Score.

Models are created lazily, once per worker process, through the factories (Demucs and Basic
Pitch take seconds to load). Temporary files live in one directory per job, removed at the end.
"""

import hashlib
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from tabforge_worker.arrange.fretting import assign_positions
from tabforge_worker.arrange.layout import build_score
from tabforge_worker.arrange.quantize import quantize
from tabforge_worker.media import MediaError, normalize_to_wav, probe_duration_s
from tabforge_worker.pipeline import (
    PipelineError,
    PipelineResult,
    Stage,
    StageCallback,
    plan_stages,
)
from tabforge_worker.ports import BeatTracker, Separator, Transcriber
from tabforge_worker.queue import ClaimedJob

MAX_DURATION_S = 600.0  # US-01: 10 minutes
STANDARD_TUNING = (64, 59, 55, 50, 45, 40)  # string 1 (high E) first


class AudioSource(Protocol):
    def download(self, key: str, dst: Path) -> None: ...


class _Lazy[T]:
    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: T | None = None

    def get(self) -> T:
        if self._value is None:
            self._value = self._factory()
        return self._value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


class RealPipeline:
    def __init__(
        self,
        source: AudioSource,
        transcriber: Callable[[], Transcriber],
        separator: Callable[[], Separator],
        beat_tracker: Callable[[], BeatTracker],
        max_duration_s: float = MAX_DURATION_S,
        tuning: tuple[int, ...] = STANDARD_TUNING,
    ) -> None:
        self._source = source
        self._transcriber = _Lazy(transcriber)
        self._separator = _Lazy(separator)
        self._beats = _Lazy(beat_tracker)
        self._max_duration_s = max_duration_s
        self._tuning = tuning

    def process(self, job: ClaimedJob, on_stage: StageCallback) -> PipelineResult:
        stages = plan_stages(job.source_kind)
        with tempfile.TemporaryDirectory(prefix="tabforge-job-") as tmp:
            work = Path(tmp)
            on_stage(Stage.NORMALIZING)
            original = work / "input"
            self._source.download(job.storage_key, original)
            sha = _sha256(original)
            try:
                duration = probe_duration_s(original, job.content_type)
                if duration > self._max_duration_s:
                    raise PipelineError(
                        "audio_too_long", f"{duration:.0f}s > {self._max_duration_s:.0f}s"
                    )
                audio = work / "audio.wav"
                normalize_to_wav(original, job.content_type, audio)
            except MediaError as exc:
                raise PipelineError("audio_unreadable", str(exc)) from exc

            guitar = audio
            if Stage.SEPARATING in stages:
                on_stage(Stage.SEPARATING)
                guitar = self._separator.get().isolate_guitar(audio, work)

            on_stage(Stage.TRANSCRIBING)
            notes = self._transcriber.get().transcribe(guitar)
            beats = self._beats.get().beats(audio)

            on_stage(Stage.ARRANGING)
            quantized = quantize(notes, beats)
            fretted = assign_positions(
                [(e.pitches, e.velocities) for e in quantized.events], self._tuning
            )
            score = build_score(quantized, fretted, self._tuning)
        return PipelineResult(score.model_dump(mode="json"), round(duration * 1000), sha)
