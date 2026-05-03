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
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, redirect, request, send_from_directory

# Reuse template + constants from content_pipeline
try:
    from content_pipeline import (
        DOMAINS,
        PIPELINE_TEMPLATE,
        PLATFORMS,
        SYSTEM_MODEL,
        SYSTEM_PROMPT,
        ensure_output_dir,
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
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = slugify(title)
        filename = f"{date_str}_{slug}.md"
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

        yield _sse({"type": "done", "file": str(filepath.relative_to(BASE_DIR))})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── FINANCE TRIGGER ─────────────────────────────────────────────────────────
# Allows a Notion page link to trigger the finance-email-check GitHub Action.
# Required env vars:
#   GITHUB_TRIGGER_TOKEN  — a GitHub PAT with "workflow" scope
#   FINANCE_TRIGGER_SECRET — a secret token embedded in the Notion link
#                            to prevent unauthorized triggers
#
# Notion link format:  https://<your-server>/trigger-finance-check?token=SECRET

@app.route("/trigger-finance-check")
def trigger_finance_check():
    expected_token = os.environ.get("FINANCE_TRIGGER_SECRET", "")
    provided_token = request.args.get("token", "")

    if not expected_token or provided_token != expected_token:
        return (
            "<h2 style='font-family:sans-serif;color:#c00'>Unauthorized.</h2>"
            "<p style='font-family:sans-serif'>Invalid or missing token.</p>",
            403,
        )

    gh_token = os.environ.get("GITHUB_TRIGGER_TOKEN", "")
    if not gh_token:
        return (
            "<h2 style='font-family:sans-serif;color:#c00'>Not configured.</h2>"
            "<p style='font-family:sans-serif'>GITHUB_TRIGGER_TOKEN is not set on this server.</p>",
            500,
        )

    api_url = (
        "https://api.github.com/repos/IrvingInsights/command-center"
        "/actions/workflows/finance-email-check.yml/dispatches"
    )
    payload = json.dumps({"ref": "main"}).encode()
    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            success = resp.status == 204
    except Exception as exc:
        return (
            f"<h2 style='font-family:sans-serif;color:#c00'>GitHub API error.</h2>"
            f"<p style='font-family:sans-serif'>{exc}</p>",
            502,
        )

    if success:
        return (
            "<html><head><meta http-equiv='refresh' content='3;url=https://github.com/"
            "IrvingInsights/command-center/actions/workflows/finance-email-check.yml'>"
            "</head><body style='font-family:sans-serif;padding:40px'>"
            "<h2 style='color:#1a7a6e'>Finance check triggered ✓</h2>"
            "<p>The GitHub Action is now running. Redirecting to the Actions log&hellip;</p>"
            "</body></html>"
        )
    return (
        "<h2 style='font-family:sans-serif;color:#c00'>Unexpected response from GitHub.</h2>",
        502,
    )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    print(f"\n  Content Pipeline server → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
