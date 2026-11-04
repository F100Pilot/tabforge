"""Download uploaded audio from S3 (same bucket and settings as the API)."""

import os
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config


class S3AudioSource:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_env(cls) -> "S3AudioSource":
        client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("TABFORGE_S3_ENDPOINT_URL") or None,
            region_name=os.environ.get("TABFORGE_S3_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("TABFORGE_S3_ACCESS_KEY") or None,
            aws_secret_access_key=os.environ.get("TABFORGE_S3_SECRET_KEY") or None,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return cls(client, os.environ.get("TABFORGE_S3_BUCKET", "tabforge-audio"))

    def download(self, key: str, dst: Path) -> None:
        self._client.download_file(self._bucket, key, str(dst))

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
