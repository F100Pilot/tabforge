import pytest

from tabforge_worker.pipeline import Stage, plan_stages


def test_mix_runs_all_stages_in_order() -> None:
    assert plan_stages("mix") == [Stage.SEPARATING, Stage.TRANSCRIBING, Stage.ARRANGING]


def test_isolated_guitar_skips_separation() -> None:
    # ADR-0002 (M0): Demucs on an isolated stem gives no gain at ~20x the CPU cost.
    assert plan_stages("guitar_stem") == [Stage.TRANSCRIBING, Stage.ARRANGING]


def test_unknown_source_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_kind"):
        plan_stages("bass")
