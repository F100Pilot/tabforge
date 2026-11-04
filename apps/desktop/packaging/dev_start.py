"""Run TabForge from a source checkout on Windows (start.bat, ADR-0008).

Prepares apps/desktop/build/bundle the same way the Windows CI does, but only what is missing
or out of date, then runs the launcher. Extra arguments go to the launcher (e.g. --smoke).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
REPO = DESKTOP.parent.parent
WEB = REPO / "apps" / "web"
BUNDLE = DESKTOP / "build" / "bundle"
WEB_STAMP = BUNDLE / "web" / ".built-from"
WEB_ENV = {
    "TABFORGE_WEB_OUTPUT": "standalone",
    "NEXT_PUBLIC_API_URL": "http://127.0.0.1:47801",
    "NEXT_PUBLIC_TABFORGE_DESKTOP": "1",
    "NEXT_TELEMETRY_DISABLED": "1",
    "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
}
# Flat node_modules (no symlinks): copying pnpm's symlinked layout dereferences it, and next then
# cannot find its own dependencies (e.g. @swc/helpers) from the copied folder.
PNPM_FLAT = ["--config.node-linker=hoisted", "--config.confirm-modules-purge=false"]
# Download name -> file that proves it is already in the bundle.
DOWNLOADS = {
    "node": BUNDLE / "node" / "node.exe",
    "postgres": BUNDLE / "pgsql" / "bin" / "pg_ctl.exe",
    "ffmpeg": BUNDLE / "ffmpeg" / "ffmpeg.exe",
}


def step(message: str) -> None:
    print(f"\n== {message}", flush=True)


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})}, check=True)  # noqa: S603


def ensure_downloads() -> None:
    missing = [name for name, marker in DOWNLOADS.items() if not marker.exists()]
    if missing:
        step(f"A descarregar: {', '.join(missing)}")
        run([sys.executable, str(DESKTOP / "packaging" / "fetch.py"), "--only", *missing], DESKTOP)


def ensure_models() -> None:
    hf = BUNDLE / "models" / "hf"
    if (hf / "hub").exists():
        return
    step("A descarregar os pesos do Demucs (uma vez)")
    code = "from demucs.pretrained import get_model; get_model('htdemucs_6s')"
    run([sys.executable, "-c", code], DESKTOP, {"HF_HOME": str(hf), "HF_HUB_OFFLINE": "0"})


def web_source_version() -> str | None:
    """Git tree hash of apps/web at HEAD: changes exactly when a pull brings web changes."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD:apps/web"],  # noqa: S607 - git from PATH, checked by start.bat
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def ensure_web() -> None:
    version = web_source_version()
    if version and WEB_STAMP.exists() and WEB_STAMP.read_text().strip() == version:
        return
    step("A compilar a interface (só quando muda)")
    node_dir = BUNDLE / "node"
    env = {**WEB_ENV, "PATH": f"{node_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    corepack = str(node_dir / "corepack.cmd")
    run([corepack, "pnpm", "install", "--frozen-lockfile", *PNPM_FLAT], WEB, env)
    run([corepack, "pnpm", "build"], WEB, env)
    target = BUNDLE / "web"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(WEB / ".next" / "standalone", target, symlinks=False)
    shutil.copytree(WEB / "public", target / "public", dirs_exist_ok=True)
    shutil.copytree(WEB / ".next" / "static", target / ".next" / "static", dirs_exist_ok=True)
    if version:
        WEB_STAMP.write_text(version)


def sync_migrations() -> None:
    target = BUNDLE / "migrations"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(REPO / "services" / "api" / "migrations", target)


def main() -> int:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    ensure_downloads()
    ensure_models()
    ensure_web()
    sync_migrations()
    os.environ["TABFORGE_BUNDLE_DIR"] = str(BUNDLE)
    step("A arrancar o TabForge")
    from tabforge_desktop.__main__ import main as launch

    return launch(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
