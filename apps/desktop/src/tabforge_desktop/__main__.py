"""`TabForge.exe`: opens the app in a window; `--smoke` runs the packaged self-test (ADR-0008)."""

import argparse
import logging
import sys
import threading
import webbrowser

from tabforge_desktop.config import BundleLayout
from tabforge_desktop.launcher import Desktop, configure_logging
from tabforge_desktop.paths import DataLayout, bundle_root, data_root

log = logging.getLogger("tabforge_desktop")


def _show_window(url: str) -> None:
    try:
        import webview
    except ImportError:
        webview = None
    if webview is None:
        # No window toolkit: use the default browser and keep serving until the process ends.
        log.warning('{"event": "webview_unavailable"}')
        webbrowser.open(url)
        threading.Event().wait()
        return
    webview.create_window("TabForge", url, width=1280, height=860, min_size=(900, 600))
    webview.start()  # blocks until the window is closed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="TabForge")
    parser.add_argument("--smoke", action="store_true", help="run the self-test and exit")
    parser.add_argument("--stub", action="store_true", help="stub pipeline (no ML), for tests")
    args = parser.parse_args(argv)

    data = DataLayout(data_root())
    configure_logging(data.logs)
    desktop = Desktop(data, BundleLayout(bundle_root()), pipeline="stub" if args.stub else "real")
    try:
        desktop.start()
        if args.smoke:
            from tabforge_desktop.smoke import run

            run(desktop.launch_token, desktop.ports.web_url)
            log.info('{"event": "smoke_ok"}')  # CI looks for this line
        else:
            _show_window(desktop.login_url())
        return 0
    except Exception:
        # Windowed build: no console, and an uncaught exception would open a blocking dialog.
        log.exception('{"event": "desktop_failed"}')
        return 1
    finally:
        desktop.stop()


if __name__ == "__main__":
    sys.exit(main())
