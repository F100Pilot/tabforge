import pytest

from tabforge_api.audio_types import AudioType, normalize_declared_type, sniff_audio_type

WAV = b"RIFF\x24\x08\x00\x00WAVEfmt "
FLAC = b"fLaC\x00\x00\x00\x22"
OGG = b"OggS\x00\x02\x00\x00"
MP3_ID3 = b"ID3\x04\x00\x00\x00\x00"
MP3_FRAME = bytes([0xFF, 0xFB, 0x90, 0x64])  # MPEG-1 Layer III


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (WAV, AudioType.WAV),
        (FLAC, AudioType.FLAC),
        (OGG, AudioType.OGG),
        (MP3_ID3, AudioType.MP3),
        (MP3_FRAME, AudioType.MP3),
    ],
)
def test_sniff_known_types(head: bytes, expected: AudioType) -> None:
    assert sniff_audio_type(head) is expected


@pytest.mark.parametrize(
    "head",
    [
        b"",
        b"RIFF\x24\x08\x00\x00AVI LIST",  # RIFF but not WAVE
        b"%PDF-1.7\n",
        b"\x89PNG\r\n\x1a\n",
        b"MZ\x90\x00",  # Windows executable
        bytes([0xFF, 0xF9, 0x00, 0x00]),  # ADTS AAC sync: layer bits 00, not MP3
        bytes([0xFF, 0x00, 0x00, 0x00]),  # incomplete sync word
    ],
)
def test_sniff_rejects_other_content(head: bytes) -> None:
    assert sniff_audio_type(head) is None


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("audio/mpeg", AudioType.MP3),
        ("audio/wav", AudioType.WAV),
        ("audio/x-wav", AudioType.WAV),
        ("audio/wave", AudioType.WAV),
        ("audio/flac", AudioType.FLAC),
        ("audio/ogg", AudioType.OGG),
        ("AUDIO/MPEG", AudioType.MP3),
        ("audio/ogg; codecs=vorbis", AudioType.OGG),
    ],
)
def test_normalize_declared_type(declared: str, expected: AudioType) -> None:
    assert normalize_declared_type(declared) is expected


@pytest.mark.parametrize("declared", ["video/mp4", "audio/aac", "application/octet-stream", ""])
def test_normalize_declared_type_rejects_unsupported(declared: str) -> None:
    assert normalize_declared_type(declared) is None
