"""Beat times with librosa's dynamic-programming beat tracker (BeatTracker port)."""

from pathlib import Path

import librosa

SAMPLE_RATE = 22050


class LibrosaBeatTracker:
    def beats(self, audio: Path) -> list[float]:
        y, sr = librosa.load(str(audio), sr=SAMPLE_RATE, mono=True)
        _, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        return [float(t) for t in librosa.frames_to_time(frames, sr=sr)]
