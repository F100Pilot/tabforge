"""Stereo "side" energy of each transcribed note (feature for arrange.split, ADR-0010).

For a stereo stem with channels L and R, mid = (L + R) / 2 and side = (L - R) / 2. A guitar in the
centre has (almost) no side energy; one panned hard to one side, or two different takes panned
left and right (doubled rhythm guitars), has about as much side as mid energy.

For each note we take short-time spectra of mid and side over the note (from its onset, at most
MAX_ANALYSIS_S) and sum the energy in narrow bands around its fundamental and first harmonics:
side_ratio = E_side / (E_mid + E_side), from 0 (centred) to 0.5 (hard-panned or decorrelated),
above 0.5 only for out-of-phase content. Only the note's own partials are measured, so a lead in
the centre and rhythm guitars at the sides playing at the same time get different ratios as long
as their partials do not overlap.

The Demucs guitar stem is written with the model's channels (2 for htdemucs_6s) and the input is
normalized to stereo (media.normalize_to_wav); Basic Pitch reads the same file as mono.
"""

from collections.abc import Sequence
from pathlib import Path

import librosa
import numpy as np

from tabforge_worker.ports import NoteEvent

N_FFT = 4096  # 93 ms at 44.1 kHz: ~11 Hz bins, enough to separate low E partials
HOP = 1024
HARMONICS = 3  # fundamental + 2 overtones
BAND_SEMITONES = 0.5  # half-width of each band around k * f0 (at least the nearest bin)
MAX_ANALYSIS_S = 0.5  # attack and early sustain; Basic Pitch offsets are unreliable anyway
# Whole-signal side/mid energy below this: the channels are the same (a mono file as stereo).
IDENTICAL_CHANNELS = 1e-6
_EPS = 1e-12


def _midi_hz(pitch: int) -> float:
    return float(440.0 * 2.0 ** ((pitch - 69) / 12))


def _band_mask(freqs: np.ndarray, pitch: int, sr: int) -> np.ndarray:
    """Bins within BAND_SEMITONES of the first HARMONICS partials (at least the nearest bin)."""
    f0 = _midi_hz(pitch)
    mask = np.zeros(freqs.shape, dtype=bool)
    for k in range(1, HARMONICS + 1):
        centre = k * f0
        if centre >= sr / 2:
            break
        lo, hi = centre * 2 ** (-BAND_SEMITONES / 12), centre * 2 ** (BAND_SEMITONES / 12)
        mask |= (freqs >= lo) & (freqs <= hi)
        mask[int(np.argmin(np.abs(freqs - centre)))] = True
    return mask


def _band_energy(x: np.ndarray, starts: range, window: np.ndarray, mask: np.ndarray) -> float:
    frames = np.zeros((len(starts), N_FFT), dtype=np.float32)
    for row, s in enumerate(starts):
        chunk = x[s : s + N_FFT]  # shorter at the end of the file: rest stays zero
        frames[row, : len(chunk)] = chunk
    spectrum = np.fft.rfft(frames * window, axis=-1)
    return float(np.sum(np.abs(spectrum[:, mask]) ** 2))


def side_ratios(signal: np.ndarray, sr: int, notes: Sequence[NoteEvent]) -> list[float] | None:
    """One side ratio per note, or None when `signal` (channels x samples) is not usable stereo."""
    if signal.ndim != 2 or signal.shape[0] != 2 or signal.shape[1] == 0:
        return None
    # float32 halves memory for a 10-minute stem (~106 MB per channel at 44.1 kHz).
    mid = ((signal[0] + signal[1]) * 0.5).astype(np.float32)
    side = ((signal[0] - signal[1]) * 0.5).astype(np.float32)
    e_side, e_mid = float(np.dot(side, side)), float(np.dot(mid, mid))
    if e_side <= IDENTICAL_CHANNELS * max(e_mid, _EPS):
        return None

    window = np.hanning(N_FFT).astype(np.float32)
    freqs = np.fft.rfftfreq(N_FFT, 1 / sr)
    last_start = max(0, len(mid) - 1)
    ratios = []
    for note in notes:
        mask = _band_mask(freqs, note.pitch, sr)
        # Frames from the onset to the analysis end, HOP apart; at least one frame.
        start = min(int(note.onset_s * sr), last_start)
        end = int(min(note.offset_s, note.onset_s + MAX_ANALYSIS_S) * sr)
        starts = range(start, max(start, end - N_FFT) + 1, HOP)
        e_m = _band_energy(mid, starts, window, mask)
        e_s = _band_energy(side, starts, window, mask)
        total = e_m + e_s
        ratios.append(e_s / total if total > _EPS else 0.0)
    return ratios


class StereoSideAnalyzer:
    """`StereoAnalyzer` reading the stem at its own sample rate, all channels."""

    def side_ratios(self, audio: Path, notes: Sequence[NoteEvent]) -> list[float] | None:
        signal, sr = librosa.load(str(audio), sr=None, mono=False)
        return side_ratios(np.atleast_2d(signal), int(sr), notes)
