import uuid

import pytest
from tabforge_score import Score

from tabforge_worker.pipeline import STUB_SCORE, Stage, StubPipeline, plan_stages
from tabforge_worker.queue import ClaimedJob


def _job(kind: str) -> ClaimedJob:
    return ClaimedJob(uuid.uuid4(), uuid.uuid4(), 1, kind, uuid.uuid4(), "audio/k", "audio/wav")


def test_mix_runs_all_stages_in_order() -> None:
    assert plan_stages("mix") == [
        Stage.NORMALIZING,
        Stage.SEPARATING,
        Stage.TRANSCRIBING,
        Stage.ARRANGING,
    ]


def test_isolated_guitar_skips_separation() -> None:
    # ADR-0002 (M0): Demucs on an isolated stem gives no gain at ~20x the CPU cost.
    assert plan_stages("guitar_stem") == [Stage.NORMALIZING, Stage.TRANSCRIBING, Stage.ARRANGING]


def test_unknown_source_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_kind"):
        plan_stages("bass")


def test_stub_pipeline_reports_stages_and_returns_valid_score() -> None:
    seen: list[Stage] = []
    result = StubPipeline().process(_job("mix"), seen.append)
    assert seen == plan_stages("mix")
    assert result.score == STUB_SCORE
    Score.model_validate(result.score)
