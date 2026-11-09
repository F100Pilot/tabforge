"""Note detection in a band mix (BabySlakh): what the "Guitarra com banda" pipeline loses.

BabySlakh (Zenodo 4603870, CC BY 4.0): 20 songs rendered from MIDI, 16 kHz, with every
instrument's stem and MIDI. The reference is the union of the notes of all guitar stems (Demucs
gives one guitar stem). Three conditions:

- `clean`: Basic Pitch on the sum of the guitar stems (no other instrument): transcription
  errors only;
- `band`: the pipeline, mix -> Demucs htdemucs_6s guitar stem -> Basic Pitch;
- `band+clean-up`: `band` followed by `arrange.clean.clean_notes` (the worker's clean-up).

Demucs stems and transcriptions are cached under <data>/eval/band/, so changing the clean-up
reruns in seconds. Onset-only note F1 (mir_eval, onset +-50 ms, pitch +-50 cents), macro mean.
The Slakh MIDI is part of Basic Pitch's training mix (see M0), so these are upper bounds.

Usage: uv run --extra ml --extra eval python eval/eval_band.py [--limit N] [--device cuda]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import fmean

import numpy as np
import pretty_midi
import soundfile
from _common import data_dir

from tabforge_worker.arrange.clean import clean_notes
from tabforge_worker.evaluation.metrics import NoteScores, score_notes
from tabforge_worker.ports import NoteEvent

_STEM = re.compile(r"^  (S\d+):\s*$")
_CLASS = re.compile(r"^    inst_class:\s*(.+?)\s*$")


def guitar_stems(track: Path) -> list[str]:
    """Stems whose `inst_class` is Guitar in metadata.yaml (read line by line: two-level keys)."""
    found: list[str] = []
    current = None
    for line in (track / "metadata.yaml").read_text().splitlines():
        if m := _STEM.match(line):
            current = m[1]
        elif (m := _CLASS.match(line)) and current and m[1] == "Guitar":
            found.append(current)
    return [
        key
        for key in found
        if (track / "stems" / f"{key}.wav").exists() and (track / "MIDI" / f"{key}.mid").exists()
    ]


def reference(track: Path, stems: list[str]) -> list[NoteEvent]:
    notes = []
    for key in stems:
        for inst in pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{key}.mid")).instruments:
            notes += [NoteEvent(n.start, n.end, n.pitch, n.velocity) for n in inst.notes]
    return sorted(notes, key=lambda n: (n.onset_s, n.pitch))


def _load(path: Path) -> list[NoteEvent]:
    return [NoteEvent(*row) for row in json.loads(path.read_text())]


def _save(path: Path, notes: list[NoteEvent]) -> None:
    path.write_text(json.dumps([[n.onset_s, n.offset_s, n.pitch, n.velocity] for n in notes]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--device")
    args = parser.parse_args()
    root = data_dir(None) / "babyslakh" / "babyslakh_16k"
    cache = data_dir(None) / "eval" / "band"
    cache.mkdir(parents=True, exist_ok=True)
    tracks = sorted(p for p in root.glob("Track*") if guitar_stems(p))
    if args.limit:
        tracks = tracks[: args.limit]
    if not tracks:
        print(f"no BabySlakh tracks with guitar under {root}", file=sys.stderr)
        return 2

    transcriber = separator = None
    scores: dict[str, list[NoteScores]] = {"clean": [], "band": [], "band+clean-up": []}
    for track in tracks:
        stems = guitar_stems(track)
        ref = reference(track, stems)
        for cond in ("clean", "band"):
            notes_path = cache / f"{track.name}-{cond}.json"
            if not notes_path.exists():
                if transcriber is None:
                    from tabforge_worker.adapters.basic_pitch import BasicPitchOnnxTranscriber

                    transcriber = BasicPitchOnnxTranscriber()
                audio = cache / f"{track.name}-{cond}.wav"
                if not audio.exists() and cond == "clean":
                    parts = [soundfile.read(track / "stems" / f"{k}.wav")[0] for k in stems]
                    length = max(len(p) for p in parts)
                    total = sum(np.pad(p, (0, length - len(p))) for p in parts)
                    soundfile.write(audio, total, soundfile.info(track / "mix.wav").samplerate)
                if not audio.exists():
                    if separator is None:
                        from tabforge_worker.adapters.demucs import DemucsGuitarSeparator

                        separator = DemucsGuitarSeparator(device=args.device)
                    stem = separator.isolate_guitar(track / "mix.wav", cache)
                    stem.rename(audio)
                _save(notes_path, transcriber.transcribe(audio))
            notes = _load(notes_path)
            scores[cond].append(score_notes(ref, notes))
            if cond == "band":
                scores["band+clean-up"].append(score_notes(ref, clean_notes(notes)))
        s = scores["band"][-1]
        c = scores["band+clean-up"][-1]
        print(
            f"{track.name}: ref {len(ref)}, band P {s.precision:.3f} R {s.recall:.3f}"
            f" F1 {s.f1:.3f} -> clean-up P {c.precision:.3f} R {c.recall:.3f} F1 {c.f1:.3f}",
            flush=True,
        )

    n_ref = sum(x.n_ref for x in scores["clean"])
    print(f"\n{len(tracks)} songs   {'P':>6} {'R':>6} {'F1':>6} {'notes':>7} (reference {n_ref})")
    for cond, rows in scores.items():
        print(
            f"{cond:<14} {fmean(r.precision for r in rows):>6.3f}"
            f" {fmean(r.recall for r in rows):>6.3f} {fmean(r.f1 for r in rows):>6.3f}"
            f" {sum(r.n_est for r in rows):>7}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
