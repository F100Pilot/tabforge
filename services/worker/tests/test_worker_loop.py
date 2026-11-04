"""Worker configuration, storage selection and the in-process loop (desktop, ADR-0008)."""

import threading
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from test_queue import _job, _job_row

from tabforge_worker.adapters.local_source import LocalAudioSource, key_path
from tabforge_worker.adapters.s3_source import S3AudioSource
from tabforge_worker.pipeline import StubPipeline
from tabforge_worker.worker import WorkerConfig, build_store, run_forever

ENV_KEYS = ("TABFORGE_STORAGE_BACKEND", "TABFORGE_LOCAL_STORAGE_DIR")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("TABFORGE_DATABASE_URL", "postgresql://u:p@localhost/db")
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_from_env_defaults_to_s3(env: pytest.MonkeyPatch) -> None:
    config = WorkerConfig.from_env()
    assert (config.storage_backend, config.local_storage_dir) == ("s3", None)
    assert isinstance(build_store(config), S3AudioSource)


def test_from_env_selects_local_storage(env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env.setenv("TABFORGE_STORAGE_BACKEND", "local")
    env.setenv("TABFORGE_LOCAL_STORAGE_DIR", str(tmp_path))
    config = WorkerConfig.from_env()
    assert (config.storage_backend, config.local_storage_dir) == ("local", tmp_path)
    assert isinstance(build_store(config), LocalAudioSource)


def test_local_storage_without_a_folder_refuses_to_start(env: pytest.MonkeyPatch) -> None:
    env.setenv("TABFORGE_STORAGE_BACKEND", "local")
    with pytest.raises(SystemExit, match="TABFORGE_LOCAL_STORAGE_DIR"):
        WorkerConfig.from_env()
    with pytest.raises(ValueError, match="local_storage_dir"):
        WorkerConfig("postgresql://x", storage_backend="local")


def test_unknown_storage_backend_refuses_to_start(env: pytest.MonkeyPatch) -> None:
    env.setenv("TABFORGE_STORAGE_BACKEND", "gcs")
    with pytest.raises(SystemExit, match="TABFORGE_STORAGE_BACKEND"):
        WorkerConfig.from_env()


class RecordingStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def download(self, key: str, dst: Path) -> None:
        raise AssertionError("stub pipeline does not download")

    def delete(self, key: str) -> None:
        self.deleted.append(key)


def test_run_forever_returns_at_once_when_already_stopped() -> None:
    stop = threading.Event()
    stop.set()
    # Unreachable database: with the flag set, the loop never connects.
    config = WorkerConfig("postgresql://u:p@127.0.0.1:1/none")
    run_forever(config, stop, pipeline=StubPipeline(), store=RecordingStore())


@pytest.mark.db
def test_run_forever_in_a_thread_processes_jobs_purges_local_files_and_stops(
    conn: psycopg.Connection[Any], database_url: str, tmp_path: Path
) -> None:
    # One expired upload with its file on disk, one queued job.
    user = conn.execute("INSERT INTO users (email) VALUES ('a@x.y') RETURNING id").fetchone()
    assert user is not None
    key = f"audio/{user[0]}/{uuid.uuid4()}"
    stored = key_path(tmp_path, key)
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"RIFF")
    conn.execute(
        "INSERT INTO audio_assets (user_id, status, source_kind, content_type, size_bytes, "
        "storage_key, expires_at) VALUES (%s, 'uploaded', 'mix', 'audio/wav', 4, %s, "
        "now() - interval '1 day')",
        (user[0], key),
    )
    job_id = _job(conn)

    config = WorkerConfig(
        database_url, poll_interval_s=0.05, storage_backend="local", local_storage_dir=tmp_path
    )
    stop = threading.Event()
    thread = threading.Thread(target=run_forever, args=(config, stop), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while _job_row(conn, job_id)[0] != "done" and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert _job_row(conn, job_id)[0] == "done"
    assert not stored.exists()
    status = conn.execute(
        "SELECT status FROM audio_assets WHERE storage_key = %s", (key,)
    ).fetchone()
    assert status == ("expired",)
