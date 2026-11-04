"""Download GuitarSet from Zenodo into the data dir, after checking its licence.

Usage: uv run python eval/download_guitarset.py [--files annotation.zip audio_mono-mic.zip]
"""

import argparse
import json
import sys
from pathlib import Path

from _common import GUITARSET_DIRNAME, GUITARSET_RECORD_ID, data_dir

from tabforge_worker.evaluation.datasets import (
    download,
    fetch_record,
    require_license,
    safe_extract,
)

# CC BY 4.0 permits use with attribution; anything else needs a human decision first.
ALLOWED_LICENSES = frozenset({"cc-by-4.0"})
DEFAULT_FILES = ("annotation.zip", "audio_mono-mic.zip")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--files", nargs="+", default=list(DEFAULT_FILES))
    args = parser.parse_args()

    root = data_dir(args.data_dir) / GUITARSET_DIRNAME
    record, raw = fetch_record(GUITARSET_RECORD_ID)
    print(f"{record.title} v{record.version} licence={record.license_id}")
    require_license(record, ALLOWED_LICENSES)

    root.mkdir(parents=True, exist_ok=True)
    (root / "zenodo-record.json").write_text(json.dumps(raw, indent=2))

    by_key = {f.key: f for f in record.files}
    missing = [k for k in args.files if k not in by_key]
    if missing:
        print(f"unknown files {missing}; available: {sorted(by_key)}", file=sys.stderr)
        return 2

    for key in args.files:
        remote = by_key[key]
        print(f"downloading {key} ({remote.size / 1e6:.0f} MB)")
        archive = download(remote, root / "archives")
        extracted = safe_extract(archive, root / Path(key).stem)
        print(f"  extracted {len(extracted)} files to {root / Path(key).stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
