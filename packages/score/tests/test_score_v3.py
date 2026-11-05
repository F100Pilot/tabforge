"""Score v3: several tracks (Lead and Rhythm, ADR-0010)."""

from typing import Any

import pytest
from pydantic import ValidationError

from tabforge_score import DEFAULT_TRACK_NAME, MAX_TRACKS, Score, ScoreTrack, to_alphatex
from tabforge_score.compare import score_events

TUNING = [64, 59, 55, 50, 45, 40]
DROP_D = [64, 59, 55, 50, 45, 38]

LEAD_BAR = {
    "beats": [
        {"duration": 4, "notes": [{"string": 1, "fret": 12}]},
        {"duration": 4, "notes": [{"string": 1, "fret": 14}]},
        {"duration": 2, "notes": []},
    ]
}
CHORD = {"duration": 2, "notes": [{"string": 6, "fret": 0}, {"string": 5, "fret": 2}]}
RHYTHM_BAR = {"beats": [CHORD, CHORD]}


def _track(name: str, *bars: dict[str, Any], **kw: Any) -> dict[str, Any]:
    track: dict[str, Any] = {"name": name, "tuning": TUNING, "bars": list(bars)}
    track.update(kw)
    return track


def _score(*tracks: dict[str, Any], **kw: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": 3,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tracks": list(tracks) or [_track("Lead", LEAD_BAR), _track("Rhythm", RHYTHM_BAR)],
    }
    doc.update(kw)
    return doc


def _v2() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "tempo_bpm": 100,
        "time_signature": [4, 4],
        "tuning": TUNING,
        "bars": [LEAD_BAR],
        "warnings": [{"bar": 1, "code": "too_many_notes", "pitch": None}],
    }


def test_v3_with_two_tracks_parses() -> None:
    score = Score.model_validate(_score())
    tracks = score.track_list()
    assert [t.name for t in tracks] == ["Lead", "Rhythm"]
    assert tracks[1].bars[0].beats[0].notes[1].fret == 2


def test_v3_round_trips_unchanged_on_the_wire() -> None:
    doc = _score(_track("Lead", LEAD_BAR, warnings=[{"bar": 1, "code": "out_of_range"}]))
    dumped = Score.model_validate(doc).model_dump(mode="json")
    assert set(dumped) == {"schema_version", "tempo_bpm", "time_signature", "tracks"}
    assert set(dumped["tracks"][0]) == {"name", "tuning", "bars", "warnings"}
    assert Score.model_validate(dumped) == Score.model_validate(doc)


def test_v2_dump_has_no_tracks_field() -> None:
    dumped = Score.model_validate(_v2()).model_dump(mode="json")
    assert set(dumped) == {
        "schema_version",
        "tempo_bpm",
        "time_signature",
        "tuning",
        "bars",
        "warnings",
    }


def test_v1_and_v2_are_one_track_named_guitarra() -> None:
    score = Score.model_validate(_v2())
    (track,) = score.track_list()
    assert track == ScoreTrack(
        name=DEFAULT_TRACK_NAME, tuning=score.tuning, bars=score.bars, warnings=score.warnings
    )
    assert DEFAULT_TRACK_NAME == "Guitarra"
    v1 = Score.model_validate({**_v2(), "schema_version": 1, "warnings": []})
    assert [t.name for t in v1.track_list()] == ["Guitarra"]


def test_one_to_four_tracks() -> None:
    assert MAX_TRACKS == 4
    Score.model_validate(_score(_track("Solo", LEAD_BAR)))
    Score.model_validate(_score(*[_track(f"G{i}", LEAD_BAR) for i in range(4)]))
    with pytest.raises(ValidationError):
        Score.model_validate(_score(*[_track(f"G{i}", LEAD_BAR) for i in range(5)]))
    with pytest.raises(ValidationError):
        Score.model_validate({**_score(), "tracks": []})


@pytest.mark.parametrize("name", ["", "x" * 41])
def test_track_name_is_1_to_40_characters(name: str) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(_score(_track(name, LEAD_BAR)))
    Score.model_validate(_score(_track("x" * 40, LEAD_BAR)))


def test_tracks_must_have_the_same_number_of_bars() -> None:
    with pytest.raises(ValidationError, match="same number of bars"):
        Score.model_validate(
            _score(_track("Lead", LEAD_BAR, LEAD_BAR), _track("Rhythm", RHYTHM_BAR))
        )


@pytest.mark.parametrize(
    "track",
    [
        _track("Rhythm", {"beats": [CHORD]}),  # bar too short
        _track("Rhythm", {"beats": [{"duration": 2, "tuplet": 3, "notes": []}, CHORD, CHORD]}),
        _track(
            "Rhythm", {"beats": [{"duration": 1, "notes": [{"string": 6, "fret": 0, "tie": True}]}]}
        ),
        _track("Rhythm", RHYTHM_BAR, warnings=[{"bar": 2, "code": "out_of_range"}]),
        _track("Rhythm", RHYTHM_BAR, tuning=TUNING[:5]),
        _track("Rhythm"),  # no bars
        _track("Rhythm", RHYTHM_BAR, extra=1),
    ],
)
def test_v2_rules_apply_to_each_track(track: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(_score(_track("Lead", LEAD_BAR), track))


def test_track_errors_name_the_track() -> None:
    with pytest.raises(ValidationError, match=r"track 2 \(Rhythm\): bar 1"):
        Score.model_validate(_score(_track("Lead", LEAD_BAR), _track("Rhythm", {"beats": [CHORD]})))


def test_ties_do_not_continue_across_tracks() -> None:
    held = {"duration": 1, "notes": [{"string": 1, "fret": 12}]}
    tied = {"duration": 1, "notes": [{"string": 1, "fret": 12, "tie": True}]}
    with pytest.raises(ValidationError, match="tie"):
        Score.model_validate(
            _score(_track("Lead", {"beats": [held]}), _track("Rhythm", {"beats": [tied]}))
        )


def test_max_bars_applies_per_track() -> None:
    bar = {"beats": [{"duration": 1, "notes": []}]}
    Score.model_validate(_score(_track("Lead", *[bar] * 2000), _track("Rhythm", *[bar] * 2000)))
    with pytest.raises(ValidationError):
        Score.model_validate(_score(_track("Lead", *[bar] * 2001)))


@pytest.mark.parametrize(
    "extra",
    [
        {"tuning": TUNING},
        {"bars": [LEAD_BAR]},
        {"warnings": []},
    ],
)
def test_v3_has_no_top_level_tuning_bars_or_warnings(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(_score(**extra))


def test_v2_has_no_tracks() -> None:
    with pytest.raises(ValidationError):
        Score.model_validate({**_v2(), "tracks": [_track("Lead", LEAD_BAR)]})


@pytest.mark.parametrize("missing", ["tuning", "bars"])
def test_v2_still_needs_tuning_and_bars(missing: str) -> None:
    doc = _v2()
    del doc[missing]
    with pytest.raises(ValidationError):
        Score.model_validate(doc)


def test_v3_alphatex_has_one_track_block_per_track() -> None:
    tex = to_alphatex(Score.model_validate(_score()), title="t")
    assert tex == (
        '\\title "t" \\tempo 100\n'
        '\\track "Lead"\n'
        "\\staff {tabs}\n"
        "\\tuning (E4 B3 G3 D3 A2 E2)\n"
        "\\ts (4 4) 12.1.4 14.1.4 r.2 |\n"
        '\\track "Rhythm"\n'
        "\\staff {tabs}\n"
        "\\tuning (E4 B3 G3 D3 A2 E2)\n"
        "\\ts (4 4) (0.6 2.5).2 (0.6 2.5).2 |"
    )


def test_v3_alphatex_uses_each_tracks_tuning_and_escapes_names() -> None:
    doc = _score(_track("Lead", LEAD_BAR), _track('Rhy "2" \\\n', RHYTHM_BAR, tuning=DROP_D))
    tex = to_alphatex(Score.model_validate(doc), title="t")
    assert '\\track "Rhy \\"2\\" \\\\ "\n\\staff {tabs}\n\\tuning (E4 B3 G3 D3 A2 D2)\n' in tex


def test_score_events_of_a_chosen_track() -> None:
    score = Score.model_validate(_score())
    assert [e.pitch for e in score_events(score)] == [76, 78]
    assert [e.pitch for e in score_events(score, track=0)] == [76, 78]
    assert sorted(e.pitch for e in score_events(score, track=1)) == [40, 40, 47, 47]


def test_score_events_track_uses_that_tracks_tuning() -> None:
    doc = _score(_track("Lead", LEAD_BAR), _track("Rhythm", RHYTHM_BAR, tuning=DROP_D))
    events = score_events(Score.model_validate(doc), track=1)
    assert sorted(e.pitch for e in events) == [38, 38, 47, 47]


@pytest.mark.parametrize("track", [2, -1])
def test_score_events_with_a_missing_track_raise_index_error(track: int) -> None:
    with pytest.raises(IndexError):
        score_events(Score.model_validate(_score()), track=track)


def test_score_events_of_v2_track_0_and_missing_track_1() -> None:
    score = Score.model_validate(_v2())
    assert score_events(score, track=0) == score_events(score)
    with pytest.raises(IndexError):
        score_events(score, track=1)
