#!/usr/bin/env python3
"""
pipeline_server.py
==================
Flask web server for the Content Pipeline UI.

Serves pipeline.html and streams Claude output back to the browser
via Server-Sent Events (SSE) so you get the same live-streaming
experience as the CLI, but in a web UI.

Usage
-----
    pip install anthropic flask
    export ANTHROPIC_API_KEY=sk-ant-...
    python pipeline_server.py

Then open: http://localhost:5005
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

# Reuse template + constants from content_pipeline
try:
    from content_pipeline import (
        DOMAINS,
        PIPELINE_TEMPLATE,
        PLATFORMS,
        SYSTEM_MODEL,
        SYSTEM_PROMPT,
        ensure_output_dir,
        save_to_notion,
        slugify,
    )
except ImportError:
    print("Error: content_pipeline.py must be in the same directory.")
    sys.exit(1)

import anthropic

# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=".", static_url_path="")
BASE_DIR = Path(__file__).parent
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "pipeline.html")


@app.route("/health")
def health():
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"status": "ok", "api_key_set": has_key}, 200


@app.route("/run", methods=["POST"])
def run():
    """
    Accepts JSON { title, platform, domain, notes }.
    Streams Claude output as SSE:
      data: {"type": "token", "text": "..."}
      data: {"type": "done", "file": "outputs/...md"}
      data: {"type": "error", "message": "..."}
    """
    body = request.get_json(force=True)
    title    = (body.get("title") or "").strip()
    platform = body.get("platform") or "LinkedIn"
    domain   = body.get("domain") or "Irving Insights"
    notes    = (body.get("notes") or "").strip() or "none"

    if not title:
        return Response(
            _sse({"type": "error", "message": "Title is required."}),
            mimetype="text/event-stream",
        )
    if platform not in PLATFORMS:
        return Response(
            _sse({"type": "error", "message": f"Invalid platform: {platform}"}),
            mimetype="text/event-stream",
        )
    if domain not in DOMAINS:
        return Response(
            _sse({"type": "error", "message": f"Invalid domain: {domain}"}),
            mimetype="text/event-stream",
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return Response(
            _sse({"type": "error", "message": "ANTHROPIC_API_KEY is not set on the server."}),
            mimetype="text/event-stream",
        )

    def generate():
        client = anthropic.Anthropic(api_key=api_key)
        user_message = PIPELINE_TEMPLATE.format(
            title=title, platform=platform, domain=domain, notes=notes
        )
        full_output = []

        try:
            with client.messages.stream(
                model=SYSTEM_MODEL,
                max_tokens=8096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            text = delta.text
                            full_output.append(text)
                            yield _sse({"type": "token", "text": text})

                stream.get_final_message()

        except anthropic.APIError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return

        # Save output
        output_text = "".join(full_output)
        output_dir = ensure_output_dir()
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        slug = slugify(title)
        filename = f"{ts}_{slug}.md"
        filepath = output_dir / filename
        header = (
            f"# {title}\n\n"
            f"**Platform:** {platform}  \n"
            f"**Domain:** {domain}  \n"
            f"**Notes:** {notes}  \n"
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n\n"
            f"---\n\n"
        )
        filepath.write_text(header + output_text, encoding="utf-8")

        notion_url = None
        notion_token = os.environ.get("NOTION_API_TOKEN")
        if notion_token:
            try:
                notion_url = save_to_notion(
                    {"title": title, "platform": platform, "domain": domain, "notes": notes},
                    output_text,
                    notion_token,
                )
            except Exception:
                pass  # non-fatal; browser can fall back to its own token

        yield _sse({"type": "done", "file": str(filepath.relative_to(BASE_DIR)), "notion_url": notion_url})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    print(f"\n  Content Pipeline server → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
