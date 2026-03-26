"""Minimal local web chat server for Step-1 conversational CAD edits.

Run:
  python scripts/step1_chat_server.py --host 127.0.0.1 --port 8765
Then open:
  http://127.0.0.1:8765/
"""

import argparse
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from readiness_check import run_readiness_check
from freecad_env_probe import run_probe
from config_manager import set_freecad_python_cmd, load_config
from auto_configure_freecad import auto_configure

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "step1_chat.html"
RUNNER_PATH = ROOT / "scripts" / "step1_chat_runner.py"


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

    def _run_runner(self, cmd: list[str]) -> tuple[dict, int]:
        result = subprocess.run(cmd, cwd=ROOT.parent, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return (
                {
                    "error": "Runner execution failed.",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
                500,
            )
        return ({"ok": True, "summary": json.loads(result.stdout)}, 200)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(UI_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/api/state":
            payload = {
                "config": load_config(),
                "readiness": run_readiness_check(),
            }
            self._send_json(payload)
            return
        if parsed.path == "/api/readiness":
            self._send_json(run_readiness_check())
            return
        if parsed.path == "/api/probe-freecad":
            self._send_json(run_probe())
            return
        if parsed.path == "/api/auto-configure-freecad":
            self._send_json(auto_configure())
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        data = json.loads(body.decode("utf-8"))

        if parsed.path == "/api/chat":
            request_text = (data.get("request_text") or "").strip()
            strict = bool(data.get("strict_freecad"))
            if not request_text:
                self._send_json({"error": "request_text is required"}, status=400)
                return
            cmd = ["python", str(RUNNER_PATH), "--request", request_text]
            if strict:
                cmd.append("--strict-freecad")
            payload, status = self._run_runner(cmd)
            self._send_json(payload, status)
            return

        if parsed.path == "/api/revert":
            payload, status = self._run_runner(["python", str(RUNNER_PATH), "--revert-last"])
            self._send_json(payload, status)
            return

        if parsed.path == "/api/save":
            payload, status = self._run_runner(["python", str(RUNNER_PATH), "--save-last"])
            self._send_json(payload, status)
            return

        if parsed.path == "/api/save-drive":
            payload, status = self._run_runner(["python", str(RUNNER_PATH), "--save-last-drive"])
            self._send_json(payload, status)
            return

        if parsed.path == "/api/config":
            freecad_python_cmd = (data.get("freecad_python_cmd") or "").strip()
            if not freecad_python_cmd:
                self._send_json({"error": "freecad_python_cmd is required"}, status=400)
                return
            cfg = set_freecad_python_cmd(freecad_python_cmd)
            self._send_json({"ok": True, "config": cfg})
            return

        if parsed.path == "/api/probe-freecad-custom":
            candidates = data.get("candidates") or []
            if not isinstance(candidates, list):
                self._send_json({"error": "candidates must be a list"}, status=400)
                return
            self._send_json(run_probe(custom_candidates=[str(x) for x in candidates]))
            return

        self._send_json({"error": "Not found"}, status=404)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Step-1 local chat server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = HTTPServer((args.host, args.port), Step1Handler)
    print(f"Step-1 chat server running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
