"""Operational commands. `python -m tabforge_api.cli init-storage` bootstraps dev object storage."""

import argparse
import sys

from tabforge_api.settings import Settings
from tabforge_api.storage import S3ObjectStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tabforge-api")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-storage", help="create the bucket and its CORS rule (dev only)")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]
    if args.command == "init-storage":
        if settings.env != "dev":
            print(
                "init-storage is for env=dev; provision storage with IaC elsewhere", file=sys.stderr
            )
            return 2
        S3ObjectStore(settings).ensure_bucket(settings.cors_origins)
        print(f"bucket {settings.s3_bucket} ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
