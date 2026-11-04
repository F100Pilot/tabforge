"""Starts and stops everything the desktop app needs, in order (ADR-0008).

Postgres -> migrations -> API (uvicorn, thread) -> worker loop (thread) -> web (Node subprocess).
Shutdown runs in reverse and always reaches Postgres, so the cluster is never left running.
"""

import logging
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tabforge_desktop.config import BundleLayout, Ports, service_env, web_env
from tabforge_desktop.paths import DataLayout
from tabforge_desktop.postgres import EmbeddedPostgres, free_port

log = logging.getLogger("tabforge_desktop")
READY_TIMEOUT_S = 90


def tail(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(sem registo)"


def wait_for(
    url: str, timeout_s: float = READY_TIMEOUT_S, failed: Callable[[], str | None] | None = None
) -> None:
    """Polls until `url` answers 2xx/3xx. `failed` returns a reason when the server has died,
    so a crash is reported at once (with its log) instead of after the whole timeout."""
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        if failed is not None and (reason := failed()) is not None:
            raise RuntimeError(f"{url}: {reason}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - fixed loopback URL
                if response.status < 400:
                    return
        except OSError as exc:  # URLError is an OSError
            last = exc
        time.sleep(0.25)
    raise TimeoutError(f"{url} not ready after {timeout_s}s: {last}")


def run_migrations(bundle: BundleLayout, database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(bundle.migrations))
    cfg.attributes["database_url"] = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    command.upgrade(cfg, "head")


PREFERRED_PORTS = Ports(web=47800, api=47801)


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_ports(preferred: Ports = PREFERRED_PORTS) -> Ports:
    """The preferred ports when both are free (stable origin: the browser keeps settings such
    as the score theme per origin); otherwise two distinct free ports. A small race is
    acceptable on a single-user PC."""
    if port_is_free(preferred.web) and port_is_free(preferred.api):
        return preferred
    web = free_port()
    api = free_port()
    while api == web:
        api = free_port()
    return Ports(web=web, api=api)


@dataclass
class Desktop:
    data: DataLayout
    bundle: BundleLayout
    pipeline: str = "real"
    launch_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    ports: Ports = field(default_factory=lambda: pick_ports())
    _stops: list[Callable[[], None]] = field(default_factory=list)
    _web: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.data.create()
        pg = EmbeddedPostgres(
            bin_dir=self.bundle.pg_bin,
            data_dir=self.data.pgdata,
            password_file=self.data.pg_password_file,
            log_file=self.data.logs / "postgres.log",
        )
        pg.ensure_initialized()
        pg.start()
        self._stops.append(pg.stop)

        env = service_env(
            self.data,
            self.bundle,
            pg.url(),
            launch_token=self.launch_token,
            upload_secret=secrets.token_urlsafe(32),
            ports=self.ports,
            pipeline=self.pipeline,
        )
        os.environ.update(env)  # Settings and WorkerConfig read the process environment
        run_migrations(self.bundle, pg.url())
        self._start_api()
        self._start_worker()
        self._start_web()
        wait_for(f"{self.ports.api_url}/ready")
        wait_for(f"{self.ports.web_url}/login", failed=self._web_failed)
        log.info('{"event": "desktop_ports", "web": %d, "api": %d}', self.ports.web, self.ports.api)
        log.info('{"event": "desktop_ready"}')

    def login_url(self) -> str:
        """Opened once by the window; the web exchanges the token for a session."""
        return f"{self.ports.web_url}/desktop#token={self.launch_token}"

    def _start_api(self) -> None:
        import uvicorn
        from tabforge_api.main import create_app

        server = uvicorn.Server(
            uvicorn.Config(create_app(), host="127.0.0.1", port=self.ports.api, log_config=None)
        )
        thread = threading.Thread(target=server.run, name="api", daemon=True)
        thread.start()

        def stop() -> None:
            server.should_exit = True
            thread.join(timeout=10)

        self._stops.append(stop)

    def _start_worker(self) -> None:
        from tabforge_worker.worker import WorkerConfig, run_forever

        stopping = threading.Event()
        thread = threading.Thread(
            target=run_forever, args=(WorkerConfig.from_env(), stopping), name="worker", daemon=True
        )
        thread.start()

        def stop() -> None:
            stopping.set()
            thread.join(timeout=30)  # a running transcription stops at its next checkpoint

        self._stops.append(stop)

    def _start_web(self) -> None:
        log_file = (self.data.logs / "web.log").open("ab")
        process = subprocess.Popen(  # noqa: S603 - bundled node and server.js, no shell
            [str(self.bundle.node), str(self.bundle.web_server)],
            cwd=self.bundle.web_server.parent,
            env={**os.environ, **web_env(self.ports)},
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._web = process

        def stop() -> None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            log_file.close()

        self._stops.append(stop)

    def _web_failed(self) -> str | None:
        if self._web is None or self._web.poll() is None:
            return None
        log_file = self.data.logs / "web.log"
        return f"web server exited with code {self._web.returncode}; {log_file}:\n{tail(log_file)}"

    def stop(self) -> None:
        while self._stops:
            stop = self._stops.pop()
            try:
                stop()
            except Exception:
                log.exception('{"event": "desktop_stop_failed"}')


def configure_logging(logs: Path) -> None:
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=logs / "tabforge.log",
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
