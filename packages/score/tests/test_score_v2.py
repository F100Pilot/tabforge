from typing import Any

import pytest
from pydantic import ValidationError

from tabforge_score import Score, beat_value, to_alphatex

TUNING = [64, 59, 55, 50, 45, 40]


def _beat(
    duration: int, *notes: tuple[int, int] | tuple[int, int, bool], **kw: Any
) -> dict[str, Any]:
    out = []
    for n in notes:
        note: dict[str, Any] = {"string": n[0], "fret": n[1]}
        if len(n) == 3:
            note["tie"] = n[2]
        out.append(note)
    return {"duration": duration, "notes": out, **kw}


def _score(*bars: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": 2,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tuning": TUNING,
        "bars": [{"beats": b} for b in bars],
    }
    doc.update(kw)
    return doc


def test_beat_value_accounts_for_dots_and_triplets() -> None:
    from fractions import Fraction

    from tabforge_score import ScoreBeat

    assert beat_value(ScoreBeat(duration=4)) == Fraction(1, 4)
    assert beat_value(ScoreBeat(duration=4, dots=1)) == Fraction(3, 8)
    assert beat_value(ScoreBeat(duration=8, tuplet=3)) == Fraction(1, 12)


def test_dotted_and_triplet_bar_is_valid_and_renders() -> None:
    bar = [
        _beat(4, (6, 0), dots=1),
        _beat(8, (6, 3)),
        _beat(8, (5, 0), tuplet=3),
        _beat(8, (5, 2), tuplet=3),
        _beat(8, (5, 3), tuplet=3),
        _beat(4, dots=0),
    ]
    tex = to_alphatex(Score.model_validate(_score(bar)), title="x")
    assert tex.endswith("\\ts (4 4) 0.6.4{d} 3.6.8 0.5.8{tu 3} 2.5.8{tu 3} 3.5.8{tu 3} r.4 |")


def test_dotted_rest_renders() -> None:
    bar = [_beat(4, dots=1), _beat(8, (6, 0)), _beat(2)]
    assert "r.4{d} 0.6.8 r.2 |" in to_alphatex(Score.model_validate(_score(bar)), title="x")


def test_tie_across_barline_renders_dash_fret() -> None:
    bars = ([_beat(2), _beat(2, (6, 0), (5, 2))], [_beat(2, (6, 0, True), (5, 2, True)), _beat(2)])
    tex = to_alphatex(Score.model_validate(_score(*bars)), title="x")
    assert "(0.6 2.5).2 | (-.6 -.5).2 r.2 |" in tex


def test_partially_tied_chord() -> None:
    bar = [_beat(2, (6, 0)), _beat(2, (6, 0, True), (4, 2))]
    assert "0.6.2 (-.6 2.4).2 |" in to_alphatex(Score.model_validate(_score(bar)), title="x")


def test_tie_must_continue_same_string_and_fret() -> None:
    with pytest.raises(ValidationError, match="tie"):
        Score.model_validate(_score([_beat(2, (6, 0)), _beat(2, (6, 3, True))]))
    with pytest.raises(ValidationError, match="tie"):
        Score.model_validate(_score([_beat(2, (6, 0)), _beat(2, (5, 0, True))]))


def test_tie_on_first_beat_is_rejected() -> None:
    with pytest.raises(ValidationError, match="tie"):
        Score.model_validate(_score([_beat(1, (6, 0, True))]))


def test_tie_after_rest_is_rejected() -> None:
    with pytest.raises(ValidationError, match="tie"):
        Score.model_validate(_score([_beat(2, (6, 0)), _beat(4), _beat(4, (6, 0, True))]))


def test_bar_value_counts_dots_and_triplets() -> None:
    short = [_beat(4, (6, 0), dots=1), _beat(2)]  # 3/8 + 1/2 = 7/8
    with pytest.raises(ValidationError, match="bar 1"):
        Score.model_validate(_score(short))


def test_triplets_must_come_in_groups_of_three_equal_beats() -> None:
    # First group mixes durations (8t, 8t, 4t).
    bad = [
        _beat(8, (6, 0), tuplet=3),
        _beat(8, (6, 0), tuplet=3),
        _beat(4, (6, 0), tuplet=3),
        _beat(8, (6, 0), tuplet=3),
        _beat(8, (6, 0), tuplet=3),
        _beat(8, (6, 0), tuplet=3),
        _beat(2),
    ]
    with pytest.raises(ValidationError, match="triplet"):
        Score.model_validate(_score(bad))


def test_dotted_triplet_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(
            _score([_beat(8, (6, 0), tuplet=3, dots=1), _beat(2), _beat(4, dots=1)])
        )


def test_warnings_are_kept() -> None:
    doc = _score(
        [_beat(1, (6, 0))],
        warnings=[{"bar": 1, "code": "out_of_range", "pitch": 30}],
    )
    score = Score.model_validate(doc)
    assert score.warnings[0].code == "out_of_range"


def test_warning_bar_must_exist() -> None:
    doc = _score([_beat(1, (6, 0))], warnings=[{"bar": 2, "code": "too_many_notes", "pitch": None}])
    with pytest.raises(ValidationError, match="warning"):
        Score.model_validate(doc)


def test_schema_v1_documents_are_still_accepted() -> None:
    doc = _score([_beat(1, (6, 0))], schema_version=1)
    assert Score.model_validate(doc).schema_version == 1
