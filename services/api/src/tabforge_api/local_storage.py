"""Desktop object storage (ADR-0008): files in one folder behind the ObjectStore port.

The browser uploads with a signed PUT to the API itself (routes/local_storage.py), standing in
for the S3 pre-signed URL. The HMAC-SHA256 signature covers method, key, expiry, Content-Type and
Content-Length, so the upload route accepts exactly what `POST /v1/uploads` authorised.

The key -> path check is duplicated in the worker (adapters/local_source.py): the two services
share only the score package (ADR-0005), and the function is small enough to test twice.
"""

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from collections.abc import AsyncIterable, Callable
from pathlib import Path
from urllib.parse import quote, urlencode

from tabforge_api.settings import MAX_PRESIGN_TTL_S, Settings
from tabforge_api.storage import ObjectInfo

LOCAL_STORAGE_PATH = "/v1/local-storage"
MAX_KEY_LENGTH = 512
# Allow-list per path segment: no separators, drive letters, NUL/control characters or spaces.
_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
# Windows device names are special in every folder, with or without an extension.
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}")


class InvalidKeyError(ValueError):
    """The object key would not map to a file inside the storage folder."""


class SignatureError(Exception):
    """The upload URL is not one this API signed, or it has expired."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class UploadSizeError(Exception):
    """The body was longer or shorter than the signed Content-Length."""


def key_path(root: Path, key: str) -> Path:
    """Map an object key to a path under `root`, refusing anything that could escape it."""
    if not key or len(key) > MAX_KEY_LENGTH:
        raise InvalidKeyError("empty or overlong key")
    parts = key.split("/")
    for part in parts:
        if (
            not _SEGMENT.fullmatch(part)
            or part.endswith(".")  # also "." and ".."; Windows drops trailing dots
            or part.split(".")[0].upper() in _WINDOWS_RESERVED
        ):
            raise InvalidKeyError("unsafe key segment")
    base = root.resolve()
    path = base.joinpath(*parts).resolve()  # follows symlinks: a link out of the root fails below
    if path == base or not path.is_relative_to(base):
        raise InvalidKeyError("key escapes the storage folder")
    return path


def upload_signature(
    secret: bytes, method: str, key: str, expires: int, content_type: str, content_length: int
) -> str:
    """Hex HMAC-SHA256 over the fields as a JSON array (unambiguous field boundaries)."""
    message = json.dumps([method.upper(), key, expires, content_type, content_length])
    return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()


def verify_upload_signature(
    secret: bytes,
    method: str,
    key: str,
    expires: str | None,
    sig: str | None,
    content_type: str,
    content_length: int,
    now: float,
) -> None:
    """Raise SignatureError unless `sig` signs exactly this request and has not expired."""
    if not expires or not expires.isdecimal() or not sig or not _HEX_SHA256.fullmatch(sig):
        raise SignatureError("invalid_signature", "missing or malformed upload signature")
    expires_at = int(expires)
    expected = upload_signature(secret, method, key, expires_at, content_type, content_length)
    if not hmac.compare_digest(expected, sig):
        raise SignatureError("invalid_signature", "upload signature does not match the request")
    if not now < expires_at <= now + MAX_PRESIGN_TTL_S:
        raise SignatureError("upload_url_expired", "the upload URL has expired")


class LocalObjectStore:
    """ObjectStore on the local filesystem. Content types are not stored (head returns None)."""

    def __init__(
        self,
        root: Path,
        secret: bytes,
        public_url: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()
        self._secret = secret
        self._public_url = public_url.rstrip("/")
        self._clock = clock

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalObjectStore":
        if settings.local_storage_dir is None or settings.local_upload_secret is None:
            raise ValueError("storage_backend=local needs local_storage_dir and upload secret")
        return cls(
            settings.local_storage_dir,
            settings.local_upload_secret.get_secret_value().encode(),
            str(settings.api_public_url),
        )

    def path(self, key: str) -> Path:
        return key_path(self._root, key)

    def presign_put(self, key: str, content_type: str, content_length: int, expires_s: int) -> str:
        if not 0 < expires_s <= MAX_PRESIGN_TTL_S:
            raise ValueError(f"expires_s must be within 1..{MAX_PRESIGN_TTL_S}")
        self.path(key)  # never sign a key the upload route would refuse
        expires = int(self._clock()) + expires_s
        sig = upload_signature(self._secret, "PUT", key, expires, content_type, content_length)
        query = urlencode({"expires": expires, "sig": sig})
        return f"{self._public_url}{LOCAL_STORAGE_PATH}/{quote(key, safe='/')}?{query}"

    def verify_put(
        self,
        key: str,
        expires: str | None,
        sig: str | None,
        content_type: str,
        content_length: int,
    ) -> None:
        self.path(key)
        verify_upload_signature(
            self._secret, "PUT", key, expires, sig, content_type, content_length, self._clock()
        )

    async def write_stream(self, key: str, chunks: AsyncIterable[bytes], length: int) -> None:
        """Write to a temp file next to the target, then rename: readers never see a partial file.

        More or fewer bytes than `length` abort the upload and delete the temp file.
        """
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")  # mode 0600
        tmp = Path(tmp_name)
        try:
            written = 0
            with os.fdopen(fd, "wb") as fh:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > length:
                        raise UploadSizeError("body is longer than the signed length")
                    fh.write(chunk)
            if written != length:
                raise UploadSizeError("body is shorter than the signed length")
            tmp.replace(path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def head(self, key: str) -> ObjectInfo | None:
        try:
            size = self.path(key).stat().st_size
        except FileNotFoundError:
            return None
        return ObjectInfo(size, None)

    def read_prefix(self, key: str, length: int) -> bytes:
        with self.path(key).open("rb") as fh:
            return fh.read(length)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
