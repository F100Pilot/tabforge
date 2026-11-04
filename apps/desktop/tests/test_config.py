import json
from pathlib import Path

from tabforge_desktop.config import API_URL, WEB_URL, BundleLayout, service_env, web_env
from tabforge_desktop.paths import DataLayout


def test_service_env_is_desktop_local_only(tmp_path: Path) -> None:
    env = service_env(
        DataLayout(tmp_path / "data"),
        BundleLayout(tmp_path / "bundle"),
        "postgresql://u:p@127.0.0.1:5/db",
        launch_token="t",
        upload_secret="s",
    )
    assert env["TABFORGE_ENV"] == "desktop"
    assert env["TABFORGE_STORAGE_BACKEND"] == "local"
    assert env["TABFORGE_LOCAL_STORAGE_DIR"] == str(tmp_path / "data" / "audio")
    assert json.loads(env["TABFORGE_CORS_ORIGINS"]) == [WEB_URL]
    assert env["TABFORGE_API_PUBLIC_URL"] == API_URL
    assert WEB_URL.startswith("http://127.0.0.1:") and API_URL.startswith("http://127.0.0.1:")
    assert env["TABFORGE_SESSION_COOKIE_SECURE"] == "false"
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["HF_HOME"].startswith(str(tmp_path / "bundle"))
    assert "TABFORGE_DEV_AUTH" not in env


def test_web_listens_on_loopback_only() -> None:
    assert web_env()["HOSTNAME"] == "127.0.0.1"


def test_wait_for_reports_a_dead_server_at_once() -> None:
    import time

    import pytest

    from tabforge_desktop.launcher import wait_for

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="exited with code 1"):
        wait_for("http://127.0.0.1:9/never", timeout_s=30, failed=lambda: "exited with code 1")
    assert time.monotonic() - start < 2


def test_tail_keeps_the_last_lines(tmp_path: Path) -> None:
    from tabforge_desktop.launcher import tail

    log = tmp_path / "web.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    assert tail(log, 2) == "line 98\nline 99"
    assert tail(tmp_path / "missing.log") == "(sem registo)"
