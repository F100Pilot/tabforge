"""Embedded PostgreSQL for the desktop app (ADR-0008).

One cluster per user in the data folder, listening only on 127.0.0.1 with a generated password.
Unix-domain sockets are disabled so nothing else on the machine can reach it by socket.
"""

import os
import secrets
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql

from tabforge_desktop.paths import executable

USER = "tabforge"
DATABASE = "tabforge"
START_TIMEOUT_S = 60
# Appended once after initdb. Port comes from the command line on each start.
_CONF = """
# TabForge desktop (ADR-0008)
listen_addresses = '127.0.0.1'
unix_socket_directories = ''
"""


def free_port() -> int:
    """A port that was free a moment ago on 127.0.0.1 (small race, acceptable locally)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)


@dataclass
class EmbeddedPostgres:
    bin_dir: Path
    data_dir: Path
    password_file: Path
    log_file: Path
    port: int | None = field(default=None, init=False)

    def _run(self, name: str, *args: str) -> None:
        subprocess.run(  # noqa: S603 - fixed executable from the bundle, no shell
            [str(executable(self.bin_dir, name)), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=START_TIMEOUT_S * 2,
        )

    @property
    def password(self) -> str:
        return self.password_file.read_text(encoding="utf-8").strip()

    def initialized(self) -> bool:
        return (self.data_dir / "PG_VERSION").exists()

    def ensure_initialized(self) -> None:
        """First run: create the cluster with a random password (scram-sha-256 only)."""
        if self.initialized():
            return
        _write_secret(self.password_file, secrets.token_urlsafe(32))
        pwfile = self.data_dir.parent / ".initdb-pw"
        _write_secret(pwfile, self.password)
        try:
            self._run(
                "initdb",
                "-D",
                str(self.data_dir),
                "-U",
                USER,
                "--auth=scram-sha-256",
                f"--pwfile={pwfile}",
                "-E",
                "UTF8",
                "--locale=C",
            )
        finally:
            pwfile.unlink(missing_ok=True)
        with (self.data_dir / "postgresql.conf").open("a", encoding="utf-8") as conf:
            conf.write(_CONF)

    def start(self) -> None:
        self.port = free_port()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            "pg_ctl",
            "-D",
            str(self.data_dir),
            "-l",
            str(self.log_file),
            "-o",
            f"-p {self.port}",
            "-w",
            "-t",
            str(START_TIMEOUT_S),
            "start",
        )
        self._ensure_database()

    def stop(self) -> None:
        if self.port is None:
            return
        self._run("pg_ctl", "-D", str(self.data_dir), "-m", "fast", "-w", "stop")
        self.port = None

    def url(self, database: str = DATABASE) -> str:
        if self.port is None:
            raise RuntimeError("postgres is not running")
        password = quote(self.password, safe="")
        return f"postgresql://{USER}:{password}@127.0.0.1:{self.port}/{database}"

    def _ensure_database(self) -> None:
        with psycopg.connect(self.url("postgres"), autocommit=True) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))
            if exists.fetchone() is None:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE)))
