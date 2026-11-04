"""Object storage behind a small port; S3 implementation via boto3 (MinIO/versitygw in dev)."""

from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from tabforge_api.settings import Settings


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None


class ObjectStore(Protocol):
    def presign_put(
        self, key: str, content_type: str, content_length: int, expires_s: int
    ) -> str: ...
    def head(self, key: str) -> ObjectInfo | None: ...
    def read_prefix(self, key: str, length: int) -> bytes: ...
    def delete(self, key: str) -> None: ...


class S3ObjectStore:
    """Signs browser URLs with the public endpoint; talks to S3 on the internal one."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client = _client(settings, settings.s3_endpoint_url)
        self._signer = _client(
            settings, settings.s3_public_endpoint_url or settings.s3_endpoint_url
        )

    def presign_put(self, key: str, content_type: str, content_length: int, expires_s: int) -> str:
        # Content-Type and Content-Length are signed: S3 rejects any other upload (403).
        url: str = self._signer.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": content_length,
            },
            ExpiresIn=expires_s,
        )
        return url

    def head(self, key: str) -> ObjectInfo | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(int(resp["ContentLength"]), resp.get("ContentType"))

    def read_prefix(self, key: str, length: int) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}")
        data: bytes = resp["Body"].read()
        return data

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def ensure_bucket(self, cors_origins: list[str]) -> None:
        """Dev bootstrap: create the bucket and allow browser PUTs from the web origins."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        if cors_origins:
            self._client.put_bucket_cors(
                Bucket=self._bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": cors_origins,
                            "AllowedMethods": ["PUT"],
                            "AllowedHeaders": ["content-type"],
                            "MaxAgeSeconds": 300,
                        }
                    ]
                },
            )


def _client(settings: Settings, endpoint: Any) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=str(endpoint) if endpoint else None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key.get_secret_value()
        if settings.s3_access_key
        else None,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value()
        if settings.s3_secret_key
        else None,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
