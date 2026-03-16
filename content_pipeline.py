#!/usr/bin/env python3
"""
content_pipeline.py
===================
Daniel Irving's CMS Overseer — content pipeline runner.

Takes a content item from idea to post-ready in one session:
  Stage 1 → Research Brief
  Stage 2 → First Draft
  Stage 3 → Editorial Pass + final copy
  Stage 4 → Posting Instructions

Usage
-----
Interactive (prompts for all inputs):
    python content_pipeline.py

With flags:
    python content_pipeline.py \
        --title "Why Camps Beat Apps" \
        --platform LinkedIn \
        --domain "Irving Insights" \
        --notes "Focus on the formation angle"

Environment
-----------
    ANTHROPIC_API_KEY — required
"""

import anthropic
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORMS = ["LinkedIn", "Substack", "X", "YouTube"]
DOMAINS = ["Irving Insights", "Book", "TBK", "SubSignal", "Personal"]
SYSTEM_MODEL = "claude-opus-4-6"

NOTION_DB_ID  = "0a6ba029-ce7b-403e-8212-ad94aa3b396f"
NOTION_API    = "https://api.notion.com/v1"
NOTION_VER    = "2022-06-28"

PLATFORM_CHANNELS: dict[str, list[str]] = {
    "LinkedIn": ["LinkedIn"],
    "Substack": ["Substack"],
    "X":        ["X"],
    "YouTube":  ["YouTube"],
}

SYSTEM_PROMPT = """You are Daniel Irving's CMS Overseer for a single content pipeline run.
Your job is to take one content item from idea to post-ready in this session —
research it, draft it, edit it, and hand off a clean posting instruction at the end.

Do not ask for clarification unless something is genuinely ambiguous.
Make reasonable decisions and flag them.
Move through all stages sequentially and show your work at each stage before proceeding."""

PIPELINE_TEMPLATE = """
CONTENT ITEM:
- Title/Idea: {title}
- Platform: {platform}
- Domain: {domain}
- Notes: {notes}

---

DANIEL'S IDENTITY (do not ask — this is fixed context):
- Principal Consultant, Irving Insights Consulting — operational strategy and values-based planning for mission-driven nonprofits
- Author-in-progress: "A Human Childhood in the Era of AI" — experiential education, formation theory, AI's impact on childhood
- 30+ years in camp-based experiential education, 12 as Camp Sisol director
- Authorial stance: witness/practitioner — not pundit, not policy advocate
- Voice models: Scott Galloway (direct, provokes thought) meets bell hooks (grounded, relational, honest)
- Philosophy: skeptical of tech solutionism; believes human formation > digital optimization
- Avoid: buzzwords, listicles, "In today's world", "As we navigate", corporate hedging, AI-sounding prose

---

## STAGE 1 — RESEARCH

Research the topic above. Search the web if needed. Produce a Research Brief with:

1. Key Findings — 3–5 bullets of what's true, current, and relevant
2. Best Angles for Daniel — 3 numbered angles ranked by fit with his voice and authority
3. Anchor — the single best story, example, or statistic to build the piece around
4. Sources — any links worth citing or saving
5. Recommended Angle — which of the 3 you'll use and why (1 sentence)

Output the Research Brief in full. Then pause and say: "Research complete. Proceeding to draft."

---

## STAGE 2 — DRAFT

Using the Research Brief above and the recommended angle, write a complete first draft.

Platform specs (apply the one that matches):
- **LinkedIn post**: 150–300 words. No headers. Paragraph breaks every 2–3 lines. End with a single question or point of reflection. No hashtags yet.
- **Substack article**: 600–1,200 words. Open with a personal scene or observation. 3 sections. Practical or reflective close.
- **X thread**: 6–9 tweets. Hook tweet under 200 chars. Each tweet standalone but builds toward a conclusion. Number them (1/, 2/, etc.).
- **YouTube script**: 800–1,500 words. Conversational register. Open with a question or scene. Two natural pause points marked [PAUSE].

Write the full draft. Do not truncate. Then pause and say: "Draft complete. Proceeding to editorial pass."

---

## STAGE 3 — EDITORIAL PASS

Review the draft against this checklist. Fix problems directly — don't just flag them:

1. **Hook** — does the first sentence earn the second? Rewrite if not.
2. **Voice** — does it sound like a human practitioner? Cut or rewrite any AI-sounding phrases.
3. **Specificity** — is there at least one concrete detail, story, or number? Add one if missing.
4. **Length** — is every sentence earning its place? Cut anything that doesn't.
5. **Ending** — does it land with a point of view? Fix if it trails off.
6. **Platform fit** — does the format and length match the platform? Adjust if not.

Output the final polished version in full. Below it, write a 2-sentence editorial note: what you changed and why.

Then suggest up to 3 hashtags if platform is LinkedIn or X. Skip for Substack and YouTube.

Then pause and say: "Final copy ready. Proceeding to posting instructions."

---

## STAGE 4 — POSTING INSTRUCTIONS

Output a clean, ready-to-execute posting block:

---
POSTING INSTRUCTIONS
Platform: {platform}
Action: Navigate to the URL below, open the composer, paste the final copy exactly as written. Do not alter it.

Platform URLs:
- LinkedIn: https://www.linkedin.com/feed/ → click "Start a post"
- Substack: https://substack.com/publish/post/new
- X / Twitter: https://x.com/compose/tweet
- YouTube: https://studio.youtube.com/

Hashtags to append (LinkedIn/X only): [list or "none"]
Visibility: Public

After posting:
1. Copy the URL of the published post
2. Return here with the Post URL
3. Log it in the Notion Content Calendar entry: {title} → Status: Published, Post URL: [paste]
---

Session complete.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60]


def ensure_output_dir() -> Path:
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir


# ---------------------------------------------------------------------------
# Notion integration
# ---------------------------------------------------------------------------

def _chunk_rich_text(text: str) -> list:
    """Split text into 1999-char blocks (Notion rich_text limit is 2000)."""
    if not text:
        return [{"text": {"content": ""}}]
    return [{"text": {"content": text[i:i + 1999]}} for i in range(0, len(text), 1999)]


def _notion_req(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{NOTION_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VER,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def save_to_notion(inputs: dict, output_text: str, token: str) -> str:
    """Create a page in SignalWorks — Content Items, add a completion comment.

    Returns the Notion page URL.
    """
    channels = [{"name": ch} for ch in PLATFORM_CHANNELS.get(inputs["platform"], [inputs["platform"]])]

    page = _notion_req("POST", "/pages", token, {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Content Item":  {"title":        [{"text": {"content": inputs["title"]}}]},
            "Stage":         {"select":        {"name": "Drafting"}},
            "Master Copy":   {"rich_text":     _chunk_rich_text(output_text)},
            "Notes":         {"rich_text":     _chunk_rich_text(inputs.get("notes", ""))},
            "Channels":      {"multi_select":  channels},
            "Human Approved":{"checkbox":      False},
        },
    })

    _notion_req("POST", "/comments", token, {
        "parent":    {"page_id": page["id"]},
        "rich_text": [{"text": {"content": "Pipeline complete. Review and check Human Approved when ready."}}],
    })

    return page.get("url", f"https://notion.so/{page['id'].replace('-', '')}")


def prompt_choice(label: str, choices: list[str]) -> str:
    """Interactive single-choice prompt."""
    print(f"\n{label}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    while True:
        raw = input("Enter number: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(choices)}.")


def gather_inputs(args: argparse.Namespace) -> dict:
    """Collect the four content item fields, from args or interactive prompts."""
    inputs = {}

    if args.title:
        inputs["title"] = args.title
    else:
        print("\n--- Content Pipeline: Input ---")
        inputs["title"] = input("Title / Idea (from Notion content calendar): ").strip()
        if not inputs["title"]:
            print("Title is required.")
            sys.exit(1)

    if args.platform:
        if args.platform not in PLATFORMS:
            print(f"Invalid platform. Choose from: {', '.join(PLATFORMS)}")
            sys.exit(1)
        inputs["platform"] = args.platform
    else:
        inputs["platform"] = prompt_choice("Platform:", PLATFORMS)

    if args.domain:
        if args.domain not in DOMAINS:
            print(f"Invalid domain. Choose from: {', '.join(DOMAINS)}")
            sys.exit(1)
        inputs["domain"] = args.domain
    else:
        inputs["domain"] = prompt_choice("Domain:", DOMAINS)

    if args.notes is not None:
        inputs["notes"] = args.notes or "none"
    else:
        raw = input("\nNotes (paste from Notion, or press Enter for none): ").strip()
        inputs["notes"] = raw if raw else "none"

    return inputs


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(inputs: dict, save: bool = True, notion: bool = True) -> str:
    """Build the prompt, stream from Claude, and return the full output."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nError: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    user_message = PIPELINE_TEMPLATE.format(
        title=inputs["title"],
        platform=inputs["platform"],
        domain=inputs["domain"],
        notes=inputs["notes"],
    )

    print("\n" + "=" * 70)
    print(f"  CMS OVERSEER — {inputs['title']}")
    print(f"  Platform: {inputs['platform']}  |  Domain: {inputs['domain']}")
    print("=" * 70 + "\n")

    full_output = []

    with client.messages.stream(
        model=SYSTEM_MODEL,
        max_tokens=8096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for event in stream:
            # Skip thinking blocks — stream only the visible text
            if event.type == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    text = delta.text
                    print(text, end="", flush=True)
                    full_output.append(text)

        stream.get_final_message()  # ensure stream is fully consumed

    output_text = "".join(full_output)
    print("\n")

    if save:
        _save_output(inputs, output_text)

    if notion:
        notion_token = os.environ.get("NOTION_API_TOKEN")
        if notion_token:
            print("Saving to Notion…", end=" ", flush=True)
            try:
                url = save_to_notion(inputs, output_text, notion_token)
                print(f"done → {url}")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode()
                print(f"⚠ Notion error {exc.code}: {body}")
            except Exception as exc:
                print(f"⚠ Notion error: {exc}")
        else:
            print("(Tip: set NOTION_API_TOKEN to auto-save to Notion)")

    return output_text


def _save_output(inputs: dict, text: str) -> None:
    """Save pipeline output as a markdown file."""
    output_dir = ensure_output_dir()
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    slug = slugify(inputs["title"])
    filename = f"{ts}_{slug}.md"
    filepath = output_dir / filename

    header = (
        f"# {inputs['title']}\n\n"
        f"**Platform:** {inputs['platform']}  \n"
        f"**Domain:** {inputs['domain']}  \n"
        f"**Notes:** {inputs['notes']}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n\n"
        f"---\n\n"
    )

    filepath.write_text(header + text, encoding="utf-8")
    print(f"Output saved → {filepath}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Daniel Irving's CMS Overseer — content pipeline runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python content_pipeline.py

  # Fully specified
  python content_pipeline.py \\
      --title "Why Camps Beat Apps" \\
      --platform LinkedIn \\
      --domain "Irving Insights" \\
      --notes "Lead with the Camp Sisol example"

  # No-save mode (outputs to terminal only)
  python content_pipeline.py --no-save
        """,
    )
    parser.add_argument("--title", help="Title or idea from Notion content calendar")
    parser.add_argument(
        "--platform",
        choices=PLATFORMS,
        help="Publishing platform",
    )
    parser.add_argument(
        "--domain",
        choices=DOMAINS,
        help="Content domain",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help='Notes from Notion entry (use "none" for no notes)',
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save output to file (print to terminal only)",
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="Skip saving to Notion even if NOTION_API_TOKEN is set",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    inputs = gather_inputs(args)
    run_pipeline(inputs, save=not args.no_save, notion=not args.no_notion)


if __name__ == "__main__":
    main()
