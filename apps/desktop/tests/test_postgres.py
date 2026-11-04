"""Runs a real cluster when TABFORGE_TEST_PG_BIN points at PostgreSQL server binaries.

initdb refuses to run as root, so CI runs this as the normal runner user.
"""

import os
from pathlib import Path

import psycopg
import pytest

from tabforge_desktop.postgres import EmbeddedPostgres, free_port

PG_BIN = os.environ.get("TABFORGE_TEST_PG_BIN")
pytestmark = pytest.mark.postgres


def test_free_port_is_bindable() -> None:
    port = free_port()
    assert 1024 <= port <= 65535


@pytest.mark.skipif(not PG_BIN or not Path(PG_BIN).is_dir(), reason="no PostgreSQL binaries")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="initdb refuses root")
def test_cluster_lifecycle(tmp_path: Path) -> None:
    pg = EmbeddedPostgres(
        bin_dir=Path(PG_BIN or ""),
        data_dir=tmp_path / "pgdata",
        password_file=tmp_path / "pg-password",
        log_file=tmp_path / "logs" / "postgres.log",
    )
    pg.ensure_initialized()
    assert pg.initialized()
    assert (tmp_path / "pg-password").stat().st_mode & 0o077 == 0
    assert not (tmp_path / ".initdb-pw").exists()
    pg.ensure_initialized()  # idempotent

    pg.start()
    try:
        with psycopg.connect(pg.url()) as conn:
            assert conn.execute("SELECT current_database()").fetchone() == ("tabforge",)
            listen = conn.execute("SHOW listen_addresses").fetchone()
            sockets = conn.execute("SHOW unix_socket_directories").fetchone()
        assert listen == ("127.0.0.1",)
        assert sockets == ("",)
        with pytest.raises(psycopg.OperationalError):
            psycopg.connect(f"postgresql://tabforge:wrong@127.0.0.1:{pg.port}/tabforge").close()
    finally:
        pg.stop()
    assert pg.port is None

    pg.start()  # restart with existing data and a new port
    pg.stop()
