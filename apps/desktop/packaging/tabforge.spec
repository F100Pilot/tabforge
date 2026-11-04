# PyInstaller spec for TabForge.exe (ADR-0008). Run from apps/desktop:
#   uv run pyinstaller packaging/tabforge.spec --noconfirm
# Expects build/bundle/{pgsql,node,web,ffmpeg,models} (packaging/fetch.py, web build, model prefetch).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent  # apps/desktop
BUNDLE = ROOT / "build" / "bundle"
MIGRATIONS = ROOT.parent.parent / "services" / "api" / "migrations"

datas = [(str(BUNDLE / name), name) for name in ("pgsql", "node", "web", "ffmpeg", "models")]
datas.append((str(MIGRATIONS), "migrations"))
for package in ("basic_pitch", "librosa", "demucs", "resampy", "webview"):
    datas += collect_data_files(package)

hiddenimports = []
for package in ("uvicorn", "tabforge_api", "tabforge_worker", "tabforge_score", "psycopg_binary"):
    hiddenimports += collect_submodules(package)

binaries = collect_dynamic_libs("psycopg_binary") + collect_dynamic_libs("onnxruntime")

a = Analysis(
    [str(ROOT / "src" / "tabforge_desktop" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tensorflow", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TabForge",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TabForge", upx=False)
