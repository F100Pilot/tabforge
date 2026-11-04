"""Pipeline contract and stages (docs/architecture.md). Real stages: real_pipeline.py."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from tabforge_worker.queue import ClaimedJob


class Stage(StrEnum):
    NORMALIZING = "normalizing"
    SEPARATING = "separating"
    TRANSCRIBING = "transcribing"
    ARRANGING = "arranging"


def plan_stages(source_kind: str) -> list[Stage]:
    """Stages for an input; an isolated guitar stem skips source separation (ADR-0002)."""
    if source_kind == "mix":
        return [Stage.NORMALIZING, Stage.SEPARATING, Stage.TRANSCRIBING, Stage.ARRANGING]
    if source_kind == "guitar_stem":
        return [Stage.NORMALIZING, Stage.TRANSCRIBING, Stage.ARRANGING]
    raise ValueError(f"unknown source_kind: {source_kind!r}")


class PipelineError(Exception):
    """A failure the user can act on; `code` is stored on the job (stable, documented)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PipelineResult:
    score: dict[str, Any]
    duration_ms: int | None = None
    sha256: str | None = None


StageCallback = Callable[[Stage], None]


class Pipeline(Protocol):
    def process(self, job: "ClaimedJob", on_stage: StageCallback) -> PipelineResult: ...


class StubPipeline:
    """M1 walking skeleton: no audio processing, a fixed score."""

    def process(self, job: "ClaimedJob", on_stage: StageCallback) -> PipelineResult:
        for stage in plan_stages(job.source_kind):
            on_stage(stage)
        return PipelineResult(STUB_SCORE)


# Fixed score written by the M1 stub pipeline: an E minor pentatonic phrase in 4/4.
# Format: tabforge_api.score.Score v1 (strings 1 = highest .. 6 = lowest).
STUB_SCORE: dict[str, Any] = {
    "schema_version": 1,
    "tempo_bpm": 96,
    "time_signature": [4, 4],
    "tuning": [64, 59, 55, 50, 45, 40],
    "bars": [
        {
            "beats": [
                {"duration": 8, "notes": [{"string": 6, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 6, "fret": 3}]},
                {"duration": 8, "notes": [{"string": 5, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 5, "fret": 2}]},
                {"duration": 8, "notes": [{"string": 4, "fret": 0}]},
                {"duration": 8, "notes": [{"string": 4, "fret": 2}]},
                {"duration": 4, "notes": [{"string": 3, "fret": 0}]},
            ]
        },
        {
            "beats": [
                {"duration": 4, "notes": [{"string": 6, "fret": 0}, {"string": 5, "fret": 2}]},
                {"duration": 4, "notes": []},
                {"duration": 2, "notes": [{"string": 1, "fret": 0}, {"string": 2, "fret": 0}]},
            ]
        },
    ],
}
