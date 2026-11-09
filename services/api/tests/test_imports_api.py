"""POST /v1/imports/youtube (ADR-0014): desktop only, MP3 stored like an upload, job queued."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_desktop import API, TOKEN, desktop_settings

from tabforge_api import youtube
from tabforge_api.auth import CSRF_HEADER
from tabforge_api.local_storage import key_path
from tabforge_api.main import create_app

pytestmark = pytest.mark.db

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
LINK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def music(tmp_path: Path) -> Path:
    return tmp_path / "Music" / "TabForge"


@pytest.fixture
def desktop(engine: Engine, database_url: str, tmp_path: Path, music: Path) -> TestClient:
    settings = desktop_settings(tmp_path / "storage", database_url=database_url, music_dir=music)
    return TestClient(create_app(settings), base_url=API)


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fake(url: str, workdir: Path, **kwargs: object) -> youtube.Downloaded:
        seen.append(url)
        path = workdir / "audio.mp3"
        path.write_bytes(MP3)
        return youtube.Downloaded(path, 'AC/DC - Back In Black: "Live"', 255.0)

    monkeypatch.setattr(youtube, "download_mp3", fake)
    return seen


def _csrf(client: TestClient) -> dict[str, str]:
    resp = client.post("/v1/auth/desktop", json={"token": TOKEN})
    return {CSRF_HEADER: resp.json()["csrf_token"]}


def test_import_stores_the_mp3_queues_a_job_and_keeps_a_copy(
    desktop: TestClient, fake_download: list[str], engine: Engine, tmp_path: Path, music: Path
) -> None:
    headers = _csrf(desktop)
    resp = desktop.post(
        "/v1/imports/youtube", json={"url": LINK, "source_kind": "mix"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert fake_download == [LINK]
    assert body["job"]["status"] == "queued"
    assert body["title"] == 'AC/DC - Back In Black: "Live"'
    saved = Path(body["mp3_path"])
    assert saved == music / "AC_DC - Back In Black_ _Live_.mp3"
    assert saved.read_bytes() == MP3
    with engine.connect() as conn:
        asset = conn.execute(
            text(
                "SELECT a.storage_key, a.content_type, a.size_bytes, a.status, a.source_kind, "
                "a.expires_at FROM audio_assets a JOIN jobs j ON j.audio_id = a.id"
            )
        ).one()
    key, content_type, size, status, kind, expires = asset
    assert (content_type, size, status, kind, expires) == (
        "audio/mpeg",
        len(MP3),
        "uploaded",
        "mix",
        None,
    )
    assert key_path(tmp_path / "storage", key).read_bytes() == MP3


def test_a_second_import_of_the_same_title_does_not_overwrite_the_copy(
    desktop: TestClient, fake_download: list[str], music: Path
) -> None:
    headers = _csrf(desktop)
    for _ in range(2):
        assert (
            desktop.post("/v1/imports/youtube", json={"url": LINK}, headers=headers).status_code
            == 201
        )
    assert sorted(p.name for p in music.iterdir()) == [
        "AC_DC - Back In Black_ _Live_ (2).mp3",
        "AC_DC - Back In Black_ _Live_.mp3",
    ]


def test_only_youtube_links_are_accepted(desktop: TestClient, fake_download: list[str]) -> None:
    headers = _csrf(desktop)
    resp = desktop.post(
        "/v1/imports/youtube", json={"url": "https://example.com/song.mp3"}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_youtube_url"
    assert fake_download == []


@pytest.mark.parametrize(
    ("code", "status"),
    [("audio_too_long", 422), ("download_failed", 502), ("unavailable", 501)],
)
def test_download_problems_map_to_clear_errors(
    desktop: TestClient, monkeypatch: pytest.MonkeyPatch, engine: Engine, code: str, status: int
) -> None:
    def failing(*args: object, **kwargs: object) -> youtube.Downloaded:
        raise youtube.YoutubeError(code, "detail")

    monkeypatch.setattr(youtube, "download_mp3", failing)
    resp = desktop.post("/v1/imports/youtube", json={"url": LINK}, headers=_csrf(desktop))
    assert resp.status_code == status
    assert resp.json()["code"] == code
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audio_assets")).scalar_one() == 0


def test_too_big_an_mp3_is_refused(
    engine: Engine, database_url: str, tmp_path: Path, fake_download: list[str]
) -> None:
    settings = desktop_settings(tmp_path, database_url=database_url, upload_max_bytes=10)
    client = TestClient(create_app(settings), base_url=API)
    resp = client.post("/v1/imports/youtube", json={"url": LINK}, headers=_csrf(client))
    assert resp.status_code == 413


def test_needs_csrf(desktop: TestClient, fake_download: list[str]) -> None:
    desktop.post("/v1/auth/desktop", json={"token": TOKEN})
    assert desktop.post("/v1/imports/youtube", json={"url": LINK}).status_code == 403


def test_not_available_online(client: TestClient, fake_download: list[str]) -> None:
    # The online app (S3, many users) does not download from YouTube: the route does not exist.
    assert client.post("/v1/imports/youtube", json={"url": LINK}).status_code in (401, 404)
    assert fake_download == []


def test_the_bundle_paths_reach_yt_dlp(
    engine: Engine, database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def capture(url: str, workdir: Path, **kwargs: object) -> youtube.Downloaded:
        seen.update(kwargs)
        (workdir / "audio.mp3").write_bytes(MP3)
        return youtube.Downloaded(workdir / "audio.mp3", "t", None)

    monkeypatch.setattr(youtube, "download_mp3", capture)
    ffmpeg = Path(shutil.which("true") or "/bin/true")
    settings = desktop_settings(
        tmp_path, database_url=database_url, ffmpeg=ffmpeg, node=ffmpeg, music_dir=tmp_path / "m"
    )
    client = TestClient(create_app(settings), base_url=API)
    assert (
        client.post("/v1/imports/youtube", json={"url": LINK}, headers=_csrf(client)).status_code
        == 201
    )
    assert seen == {"ffmpeg": ffmpeg, "node": ffmpeg, "max_duration_s": 600.0}
