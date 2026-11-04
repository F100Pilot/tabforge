"""Guitar source separation with Demucs `htdemucs_6s` (ADR-0002)."""

from pathlib import Path

import torch
from demucs.api import Separator as DemucsApiSeparator
from demucs.audio import save_audio

GUITAR_STEM = "guitar"


class DemucsGuitarSeparator:
    """`Separator` returning the `guitar` stem of a 6-source Demucs model as WAV.

    Weights are fetched by Demucs on first use (HuggingFace hub, then
    dl.fbaipublicfiles.com) unless `repo` points at a local model folder.
    """

    def __init__(
        self,
        model: str = "htdemucs_6s",
        device: str | None = None,
        repo: Path | None = None,
        shifts: int = 1,
    ) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._separator = DemucsApiSeparator(
            model=model, repo=repo, device=self.device, shifts=shifts, progress=False
        )
        sources = list(self._separator.model.sources)
        if GUITAR_STEM not in sources:
            raise ValueError(f"model {model!r} has no {GUITAR_STEM!r} source: {sources}")

    def isolate_guitar(self, audio: Path, workdir: Path) -> Path:
        _, stems = self._separator.separate_audio_file(audio)
        out = workdir / f"{audio.stem}_{GUITAR_STEM}.wav"
        save_audio(stems[GUITAR_STEM].cpu(), out, samplerate=self._separator.samplerate)
        return out
