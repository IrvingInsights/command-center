"""Workable local web server for Step-1 conversational CAD edits."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "step1_chat_v2.html"
RUNNER_PATH = ROOT / "scripts" / "step1_chat_runner_v2.py"
READINESS_PATH = ROOT / "scripts" / "readiness_check.py"


class Step1Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _run_python(self, script: Path, args: list[str]) -> tuple[dict, int]:
        cmd = [sys.executable, str(script), *args]
        result = subprocess.run(cmd, cwd=ROOT.parent, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return ({
                "ok": False,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }, 500)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"ok": True, "stdout": result.stdout, "stderr": result.stderr}
        return (payload, 200)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(UI_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/api/state":
            payload, status = self._run_python(READINESS_PATH, [])
            self._send_json(payload, status)
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        data = json.loads(body.decode("utf-8"))

        if parsed.path == "/api/chat":
            request_text = str(data.get("request_text") or "").strip()
            strict = bool(data.get("strict_freecad"))
            if not request_text:
                self._send_json({"error": "request_text is required"}, status=400)
                return
            args = ["--request", request_text]
            if strict:
                args.append("--strict-freecad")
            payload, status = self._run_python(RUNNER_PATH, args)
            self._send_json(payload, status)
            return

        if parsed.path == "/api/revert":
            strict = bool(data.get("strict_freecad"))
            args = ["--revert-last"]
            if strict:
                args.append("--strict-freecad")
            payload, status = self._run_python(RUNNER_PATH, args)
            self._send_json(payload, status)
            return

        self._send_json({"error": "Not found"}, status=404)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Step-1 chat server v2")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = HTTPServer((args.host, args.port), Step1Handler)
    print(f"Step-1 chat server v2 running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
