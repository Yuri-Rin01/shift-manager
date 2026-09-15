"""Windows EXE entry point: start the admin app and open the browser."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_port(host: str, candidates: tuple[int, ...]) -> int:
    for port in candidates:
        if _port_free(host, port):
            return port
    raise RuntimeError(f"利用可能なポートがありません: {candidates}")


def _open_browser(url: str, delay: float = 1.4) -> None:
    def _run() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    # Ensure DB and relative writes go next to the EXE / project root
    from app_paths import data_root

    root = data_root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    host = "127.0.0.1"
    port = _pick_port(host, (8000, 8010, 8003))
    url = f"http://{host}:{port}/"

    print("=" * 56)
    print("  シフト作成システム")
    print("=" * 56)
    print(f"  URL : {url}")
    print(f"  データ: {root / 'shift.db'}")
    print("  終了: このウィンドウを閉じる")
    print("=" * 56)
    print()

    _open_browser(url)

    import uvicorn

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
