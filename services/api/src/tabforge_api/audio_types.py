"""Accepted audio formats (US-01) and content sniffing by magic bytes (threat model T1)."""

from enum import StrEnum

SNIFF_BYTES = 12  # enough for every signature below


class AudioType(StrEnum):
    MP3 = "audio/mpeg"
    WAV = "audio/wav"
    FLAC = "audio/flac"
    OGG = "audio/ogg"


_DECLARED_ALIASES: dict[str, AudioType] = {
    "audio/mpeg": AudioType.MP3,
    "audio/mp3": AudioType.MP3,
    "audio/wav": AudioType.WAV,
    "audio/x-wav": AudioType.WAV,
    "audio/wave": AudioType.WAV,
    "audio/vnd.wave": AudioType.WAV,
    "audio/flac": AudioType.FLAC,
    "audio/x-flac": AudioType.FLAC,
    "audio/ogg": AudioType.OGG,
}


def normalize_declared_type(content_type: str) -> AudioType | None:
    """Map a client-declared MIME type (parameters ignored) to a supported type."""
    media_type = content_type.split(";", 1)[0].strip().lower()
    return _DECLARED_ALIASES.get(media_type)


def sniff_audio_type(head: bytes) -> AudioType | None:
    """Identify the real format from the first bytes of a file; None if unsupported."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return AudioType.WAV
    if head[:4] == b"fLaC":
        return AudioType.FLAC
    if head[:4] == b"OggS":
        return AudioType.OGG
    if head[:3] == b"ID3" or _is_mpeg_audio_frame(head):
        return AudioType.MP3
    return None


def _is_mpeg_audio_frame(head: bytes) -> bool:
    # 11-bit frame sync, then version (2 bits) and layer (2 bits); layer 00 is reserved
    # (and is what ADTS/AAC uses), so it is not MPEG audio.
    if len(head) < 2 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return False
    version = (head[1] >> 3) & 0b11
    layer = (head[1] >> 1) & 0b11
    return version != 0b01 and layer != 0b00
