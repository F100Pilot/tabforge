import pytest

from tabforge_worker.ports import NoteEvent


def test_valid_note_event() -> None:
    note = NoteEvent(onset_s=0.5, offset_s=1.0, pitch=64, velocity=90)
    assert note.pitch == 64


@pytest.mark.parametrize(
    ("onset", "offset", "pitch", "velocity"),
    [
        (0.0, 1.0, 128, 90),
        (0.0, 1.0, -1, 90),
        (0.0, 1.0, 60, 200),
        (1.0, 1.0, 60, 90),
        (-0.1, 1.0, 60, 90),
    ],
)
def test_invalid_note_event_rejected(
    onset: float, offset: float, pitch: int, velocity: int
) -> None:
    with pytest.raises(ValueError):
        NoteEvent(onset_s=onset, offset_s=offset, pitch=pitch, velocity=velocity)
