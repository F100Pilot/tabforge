from typing import Any

import pytest

from tabforge_worker.evaluation.guitarset import (
    STANDARD_TUNING,
    GuitarNote,
    TrackInfo,
    parse_jams,
    parse_track_id,
)


def _jams(per_string: dict[int, list[tuple[float, float, float]]]) -> dict[str, Any]:
    """Minimal JAMS doc: one note_midi annotation per string, (time, duration, midi)."""
    annotations: list[dict[str, Any]] = [
        {"namespace": "beat_position", "annotation_metadata": {}, "data": []},
    ]
    for string in range(6):
        annotations.append(
            {
                "namespace": "note_midi",
                "annotation_metadata": {"data_source": str(string)},
                "data": [
                    {"time": t, "duration": d, "value": v, "confidence": None}
                    for t, d, v in per_string.get(string, [])
                ],
            }
        )
    return {"annotations": annotations}


def test_standard_tuning_is_e2_to_e4() -> None:
    assert STANDARD_TUNING == (40, 45, 50, 55, 59, 64)


def test_parse_jams_maps_string_and_fret_sorted_by_onset() -> None:
    doc = _jams({0: [(1.0, 0.5, 43.1)], 5: [(0.2, 0.3, 64.0)], 2: [(1.0, 0.2, 52.0)]})

    notes = parse_jams(doc)

    assert notes == [
        GuitarNote(onset_s=0.2, offset_s=0.5, pitch=64, string=5, fret=0),
        GuitarNote(onset_s=1.0, offset_s=1.5, pitch=43, string=0, fret=3),
        GuitarNote(onset_s=1.0, offset_s=1.2, pitch=52, string=2, fret=2),
    ]


def test_parse_jams_rounds_continuous_midi_to_nearest_semitone() -> None:
    notes = parse_jams(_jams({4: [(0.0, 1.0, 60.49)], 3: [(0.0, 1.0, 56.51)]}))
    assert sorted(n.pitch for n in notes) == [57, 60]


def test_parse_jams_uses_data_source_not_annotation_order() -> None:
    doc = _jams({1: [(0.0, 1.0, 45.0)]})
    note_annos = [a for a in doc["annotations"] if a["namespace"] == "note_midi"]
    doc["annotations"] = [doc["annotations"][0], *reversed(note_annos)]

    (note,) = parse_jams(doc)

    assert (note.string, note.fret) == (1, 0)


def test_parse_jams_rejects_missing_string_annotation() -> None:
    doc = _jams({})
    doc["annotations"] = doc["annotations"][:-1]
    with pytest.raises(ValueError, match="6 note_midi"):
        parse_jams(doc)


def test_parse_jams_rejects_duplicate_string() -> None:
    doc = _jams({})
    doc["annotations"][-1]["annotation_metadata"]["data_source"] = "0"
    with pytest.raises(ValueError, match="strings"):
        parse_jams(doc)


@pytest.mark.parametrize("midi", [39.0, 40.0 + 25])
def test_parse_jams_rejects_fret_out_of_range(midi: float) -> None:
    with pytest.raises(ValueError, match="fret"):
        parse_jams(_jams({0: [(0.0, 1.0, midi)]}))


def test_parse_jams_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError, match="duration"):
        parse_jams(_jams({0: [(0.0, 0.0, 40.0)]}))


@pytest.mark.parametrize(
    ("track_id", "expected"),
    [
        ("00_BN1-129-Eb_comp", TrackInfo("00_BN1-129-Eb_comp", "00", "BN", "comp")),
        ("05_Funk2-108-Eb_solo", TrackInfo("05_Funk2-108-Eb_solo", "05", "Funk", "solo")),
        ("03_SS3-84-Bb_comp", TrackInfo("03_SS3-84-Bb_comp", "03", "SS", "comp")),
    ],
)
def test_parse_track_id(track_id: str, expected: TrackInfo) -> None:
    assert parse_track_id(track_id) == expected


@pytest.mark.parametrize("track_id", ["", "00_BN1-129-Eb", "x0_BN1-129-Eb_comp", "00_1-1_solo"])
def test_parse_track_id_rejects_malformed(track_id: str) -> None:
    with pytest.raises(ValueError):
        parse_track_id(track_id)
