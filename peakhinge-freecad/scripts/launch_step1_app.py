"""Launch the Step-1 web app and open browser automatically.

This helper exists so users can start the interface without manually using curl/CLI workflows.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = ROOT / "scripts" / "step1_chat_server.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Step-1 app server and open browser.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Start server without opening browser.")
    parser.add_argument("--timeout-seconds", type=float, default=12.0, help="How long to wait for server startup.")
    return parser.parse_args()


def _wait_for_server(url: str, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def main() -> None:
    args = parse_args()
    url = f"http://{args.host}:{args.port}/"
    cmd = [sys.executable, str(SERVER_SCRIPT), "--host", args.host, "--port", str(args.port)]

    proc = subprocess.Popen(cmd, cwd=ROOT.parent)
    print(f"Starting Step-1 app at {url}")
    print(f"Server command: {' '.join(cmd)}")

    try:
        if _wait_for_server(url, args.timeout_seconds):
            if not args.no_browser:
                webbrowser.open(url)
        else:
            print(f"Warning: server did not respond within {args.timeout_seconds:.1f}s at {url}")
        proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down Step-1 app.")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
