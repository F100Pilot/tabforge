"""GuitarSet JAMS parsing (https://github.com/marl/GuitarSet).

Each JAMS file has six `note_midi` annotations, one per string; `data_source` holds the
string index (0 = low E ... 5 = high E). Note values are continuous MIDI pitch.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# MIDI pitch of each open string, low E (index 0) to high E (index 5).
STANDARD_TUNING: tuple[int, ...] = (40, 45, 50, 55, 59, 64)
MAX_FRET = 24

_TRACK_ID = re.compile(r"^(?P<player>\d{2})_(?P<style>[A-Za-z]+)\d+-[^_]+_(?P<mode>comp|solo)$")


@dataclass(frozen=True, slots=True)
class GuitarNote:
    """Reference note with tablature position."""

    onset_s: float
    offset_s: float
    pitch: int
    string: int
    fret: int


@dataclass(frozen=True, slots=True)
class TrackInfo:
    track_id: str
    player: str
    style: str
    mode: str


def parse_track_id(track_id: str) -> TrackInfo:
    """Parse e.g. `00_BN1-129-Eb_comp` into player, style and comp/solo mode."""
    match = _TRACK_ID.match(track_id)
    if match is None:
        raise ValueError(f"not a GuitarSet track id: {track_id!r}")
    return TrackInfo(track_id, match["player"], match["style"], match["mode"])


def parse_jams(doc: Mapping[str, Any]) -> list[GuitarNote]:
    """Extract per-string reference notes from a loaded GuitarSet JAMS document."""
    annotations = [a for a in doc["annotations"] if a["namespace"] == "note_midi"]
    if len(annotations) != len(STANDARD_TUNING):
        raise ValueError(f"expected 6 note_midi annotations, got {len(annotations)}")

    strings = [int(a["annotation_metadata"]["data_source"]) for a in annotations]
    if sorted(strings) != list(range(len(STANDARD_TUNING))):
        raise ValueError(f"note_midi data_source must cover strings 0-5, got {strings}")

    notes: list[GuitarNote] = []
    for string, annotation in zip(strings, annotations, strict=True):
        for obs in annotation["data"]:
            notes.append(_to_note(string, float(obs["time"]), float(obs["duration"]), obs["value"]))
    return sorted(notes, key=lambda n: (n.onset_s, n.string))


def _to_note(string: int, onset: float, duration: float, value: Any) -> GuitarNote:
    if duration <= 0:
        raise ValueError(f"non-positive duration {duration} at {onset:.3f}s, string {string}")
    pitch = round(float(value))
    fret = pitch - STANDARD_TUNING[string]
    if not 0 <= fret <= MAX_FRET:
        raise ValueError(f"fret {fret} out of range at {onset:.3f}s, string {string}")
    return GuitarNote(onset, onset + duration, pitch, string, fret)
