"""Desktop upload target (ADR-0008): the signed PUT that stands in for the S3 pre-signed URL.

Registered only with storage_backend=local. The signature is the authorisation (no cookie, no
CSRF token), exactly like an S3 pre-signed URL: it binds method, key, expiry, Content-Type and
Content-Length, and the body is cut off at the signed length.
"""

from fastapi import APIRouter, Request, Response

from tabforge_api.local_storage import (
    LOCAL_STORAGE_PATH,
    InvalidKeyError,
    LocalObjectStore,
    SignatureError,
    UploadSizeError,
)
from tabforge_api.problems import ProblemError

router = APIRouter(prefix=LOCAL_STORAGE_PATH, tags=["uploads"])


@router.put("/{key:path}")
async def put_object(
    key: str, request: Request, expires: str | None = None, sig: str | None = None
) -> Response:
    """200 with an empty body on success, like S3."""
    store: LocalObjectStore = request.app.state.store
    raw_length = request.headers.get("content-length")
    if raw_length is None or not raw_length.isdecimal():
        raise ProblemError(411, "length_required", "Content-Length is required")
    length = int(raw_length)
    try:
        store.verify_put(key, expires, sig, request.headers.get("content-type", ""), length)
    except InvalidKeyError as exc:
        raise ProblemError(400, "invalid_key", "invalid object key") from exc
    except SignatureError as exc:
        raise ProblemError(403, exc.code, exc.detail) from exc
    try:
        await store.write_stream(key, request.stream(), length)
    except UploadSizeError as exc:
        raise ProblemError(400, "upload_size_mismatch", str(exc)) from exc
    return Response(status_code=200)
