"""Packaged-app smoke test (CI on Windows, ADR-0008): one real transcription through the API.

Uses only the standard library, like a browser would: launch-token login, signed local upload,
job polling, then the tab and the web server.
"""

import http.cookiejar
import io
import json
import math
import struct
import time
import urllib.request
import wave
from typing import Any

JOB_TIMEOUT_S = 900


def guitar_like_wav(seconds: float = 6.0, rate: int = 22050) -> bytes:
    """Plucked tones (E3, G3, B3, E4 repeating) with decay: enough for Basic Pitch to find notes."""
    pitches = [52, 55, 59, 64]
    note_s = 0.5
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        n = int(t / note_s)
        local = t - n * note_s
        freq = 440.0 * 2 ** ((pitches[n % len(pitches)] - 69) / 12)
        envelope = math.exp(-6 * local)
        sample = sum(math.sin(2 * math.pi * freq * k * t) / k for k in (1, 2, 3)) * envelope
        frames += struct.pack("<h", int(max(-1.0, min(1.0, 0.4 * sample)) * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


class Client:
    """Talks to the web origin only, exactly like the window: /v1 goes through proxy.ts."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.csrf: str | None = None

    def call(
        self,
        method: str,
        url: str,
        body: Any = None,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Origin": self.base, **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        if self.csrf and method != "GET" and url.startswith(self.base + "/v1/") and raw is None:
            h["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(url, data=data, method=method, headers=h)  # noqa: S310
        with self.opener.open(request, timeout=30) as response:
            text = response.read().decode() or "null"
            return json.loads(text) if "json" in response.headers.get("Content-Type", "") else None


def run(launch_token: str, base: str) -> None:
    client = Client(base)
    api = f"{base}/v1"
    session = client.call("POST", f"{api}/auth/desktop", {"token": launch_token})
    client.csrf = session["csrf_token"]

    audio = guitar_like_wav()
    upload = client.call(
        "POST",
        f"{api}/uploads",
        {"content_type": "audio/wav", "size_bytes": len(audio), "source_kind": "guitar_stem"},
    )
    client.call("PUT", upload["upload_url"], raw=audio, headers=upload["headers"])
    job = client.call("POST", f"{api}/uploads/{upload['audio_id']}/complete", {})

    deadline = time.monotonic() + JOB_TIMEOUT_S
    while job["status"] not in ("done", "failed"):
        if time.monotonic() > deadline:
            raise TimeoutError(f"job still {job['status']}/{job['stage']}")
        time.sleep(2)
        job = client.call("GET", f"{api}/jobs/{job['id']}")
    if job["status"] != "done":
        raise RuntimeError(f"job failed: {job['error_code']}")

    tab = client.call("GET", f"{api}/tabs/{job['tab_id']}")
    if not tab.get("alphatex", "").strip():
        raise RuntimeError("tab without alphaTex")
    client.call("GET", f"{base}/login")
