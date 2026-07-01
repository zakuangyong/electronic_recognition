from __future__ import annotations

import argparse
import os
import socket
import time
import urllib.request
import webbrowser
from pathlib import Path
from threading import Thread

import uvicorn

from .runtime import project_root, web_dist_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ElectronicRecognition",
        description="Start the packaged Electronic Recognition web app.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8892)
    parser.add_argument(
        "--project-root",
        default="",
        help="Runtime directory for .env, data/, result/, and logs/.",
    )
    parser.add_argument(
        "--web-dist",
        default="",
        help="Built frontend directory. Defaults to bundled web_dist/.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    parser.add_argument(
        "--strict-port",
        action="store_true",
        help="Fail instead of choosing the next free port.",
    )
    args = parser.parse_args()

    runtime_root = (
        Path(args.project_root).expanduser().resolve()
        if args.project_root
        else project_root()
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ER_PROJECT_ROOT", str(runtime_root))
    os.chdir(runtime_root)

    host = str(args.host)
    port = int(args.port)
    if not _port_is_available(host, port):
        if args.strict_port:
            raise SystemExit(f"Port {host}:{port} is already in use.")
        port = _next_available_port(host, port + 1)

    from .api import app, enable_production_frontend

    dist_dir = Path(args.web_dist).expanduser().resolve() if args.web_dist else web_dist_dir()
    mounted_dist = enable_production_frontend(dist_dir)

    url = f"http://{host}:{port}/"
    print(f"Runtime root: {runtime_root}")
    print(f"Frontend dist: {mounted_dist}")
    print(f"Listening on:  {url}")

    if not args.no_browser:
        Thread(
            target=_open_browser_when_ready,
            args=(url,),
            daemon=True,
        ).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _next_available_port(host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 50):
        if _port_is_available(host, port):
            return port
    raise SystemExit("No available local port found.")


def _open_browser_when_ready(url: str) -> None:
    health_url = f"{url.rstrip('/')}/health"
    for _ in range(60):
        try:
            with urllib.request.urlopen(health_url, timeout=1):
                webbrowser.open(url)
                return
        except Exception:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
