# M0 eval: transcription quality spike

Measures Demucs `htdemucs_6s` + Basic Pitch (ONNX) against GuitarSet's string/fret annotations.
All data goes to `<repo>/data/` (git-ignored) or `$TABFORGE_DATA_DIR`. Never commit audio.

```bash
cd services/worker
uv sync --extra ml --extra eval
uv run python eval/download_guitarset.py                      # annotation + mic audio (~GBs)
uv run python eval/run_m0.py --audio mic                      # isolated guitar
uv run python eval/run_m0.py --audio mic --separate --every 6 # through Demucs (subset)
uv run python eval/profile_m0.py --source <wav> --durations 60 180
```

- Licence: `download_guitarset.py` reads the Zenodo record and aborts unless the licence is
  `cc-by-4.0`; files are md5-verified. The record JSON is kept in `data/guitarset/` for provenance.
- Metrics: `mir_eval.transcription`, onset ±50 ms, pitch ±50 cents; reported without offset and
  with offset (20% of duration, min 50 ms). Macro average over tracks.
- Network: needs `zenodo.org` (dataset) and, for Demucs weights, `huggingface.co`
  (`adefossez/HTDemucs-6s`, safetensors) or the fallback `dl.fbaipublicfiles.com`.
- Results: `data/eval/m0-*.json`; the summary goes in `docs/eval/M0-baseline.md`.
