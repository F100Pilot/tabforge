from pathlib import Path

import pytest

from tabforge_desktop.paths import DataLayout, data_root, executable


def test_windows_data_root_is_under_localappdata() -> None:
    root = data_root({"LOCALAPPDATA": r"C:\Users\p\AppData\Local"}, platform="win32")
    assert root == Path(r"C:\Users\p\AppData\Local") / "TabForge"


def test_windows_without_localappdata_fails_closed() -> None:
    with pytest.raises(RuntimeError):
        data_root({}, platform="win32")


def test_override_wins_everywhere(tmp_path: Path) -> None:
    env = {"TABFORGE_DATA_DIR": str(tmp_path), "LOCALAPPDATA": "x"}
    assert data_root(env, platform="win32") == tmp_path
    assert data_root(env, platform="linux") == tmp_path


def test_linux_uses_xdg_data_home() -> None:
    assert data_root({"XDG_DATA_HOME": "/d"}, platform="linux") == Path("/d/tabforge")
    assert data_root({"HOME": "/h"}, platform="linux") == Path("/h/.local/share/tabforge")


def test_layout_creates_folders(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "TabForge")
    layout.create()
    assert layout.audio.is_dir() and layout.logs.is_dir()
    assert layout.pgdata.parent == layout.root


def test_executable_suffix() -> None:
    assert executable(Path("bin"), "initdb", platform="win32") == Path("bin/initdb.exe")
    assert executable(Path("bin"), "initdb", platform="linux") == Path("bin/initdb")
