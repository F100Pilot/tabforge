import json
from pathlib import Path

import pytest

from tabforge_desktop.config import BundleLayout, Ports, service_env, web_env
from tabforge_desktop.paths import DataLayout


def test_service_env_is_desktop_local_only(tmp_path: Path) -> None:
    env = service_env(
        DataLayout(tmp_path / "data"),
        BundleLayout(tmp_path / "bundle"),
        "postgresql://u:p@127.0.0.1:5/db",
        launch_token="t",
        upload_secret="s",
        ports=Ports(web=50001, api=50002),
    )
    assert env["TABFORGE_ENV"] == "desktop"
    assert env["TABFORGE_STORAGE_BACKEND"] == "local"
    assert env["TABFORGE_LOCAL_STORAGE_DIR"] == str(tmp_path / "data" / "audio")
    assert json.loads(env["TABFORGE_CORS_ORIGINS"]) == ["http://127.0.0.1:50001"]
    # Uploads go to the web origin, which proxies /v1 to the API.
    assert env["TABFORGE_API_PUBLIC_URL"] == "http://127.0.0.1:50001"
    assert env["TABFORGE_SESSION_COOKIE_SECURE"] == "false"
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["HF_HOME"].startswith(str(tmp_path / "bundle"))
    assert "TABFORGE_DEV_AUTH" not in env


def test_web_listens_on_loopback_and_knows_the_api() -> None:
    env = web_env(Ports(web=50001, api=50002))
    assert env["HOSTNAME"] == "127.0.0.1"
    assert env["PORT"] == "50001"
    assert env["TABFORGE_API_INTERNAL_URL"] == "http://127.0.0.1:50002"


def test_ports_must_differ() -> None:
    with pytest.raises(ValueError):
        Ports(web=50001, api=50001)


def test_pick_ports_keeps_the_preferred_pair_when_free() -> None:
    from tabforge_desktop.launcher import pick_ports
    from tabforge_desktop.postgres import free_port

    preferred = Ports(web=free_port(), api=free_port())
    if preferred.web != preferred.api:
        assert pick_ports(preferred) == preferred


def test_pick_ports_moves_away_from_a_busy_port() -> None:
    import socket

    from tabforge_desktop.launcher import pick_ports

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        ports = pick_ports(Ports(web=taken, api=taken + 1 if taken < 65535 else taken - 1))
    assert taken not in (ports.web, ports.api)
    assert ports.web != ports.api


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
