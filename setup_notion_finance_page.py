"""
setup_notion_finance_page.py
============================
One-time script: adds the Finance Email Cross-Check section to the
Notion Finance Dashboard page.  Run via GitHub Actions (see
.github/workflows/setup-notion-finance-page.yml).

Environment variables
---------------------
NOTION_API_TOKEN          — Notion integration secret
FINANCE_PAGE_ID           — Finance Dashboard page ID (without dashes)
FINANCE_TRIGGER_URL       — Full trigger URL for the "Run Now" link
"""

import json
import os
import urllib.request

TOKEN   = os.environ["NOTION_API_TOKEN"]
PAGE_ID = os.environ.get("FINANCE_PAGE_ID", "24846ef5886245f78fef02152df823d6")
TRIGGER_URL = os.environ.get(
    "FINANCE_TRIGGER_URL",
    "https://irving-mvp.onrender.com/trigger-finance-check?token=irving2026",
)

BLOCKS = {
    "children": [
        {
            "object": "block",
            "type": "divider",
            "divider": {},
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "📧 Finance Email Cross-Check"}}
                ],
                "color": "default",
            },
        },
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": (
                                "Scans Gmail for financial notification emails and flags "
                                "any amounts missing from your Finta/Notion transactions. "
                                "Runs automatically every Monday at 9 AM ET.\n\n"
                            )
                        },
                    },
                    {
                        "type": "text",
                        "text": {"content": "▶  Run Finance Check Now", "link": {"url": TRIGGER_URL}},
                        "annotations": {"bold": True},
                    },
                ],
                "icon": {"type": "emoji", "emoji": "🔍"},
                "color": "blue_background",
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": (
                                "After tapping the link above you will be redirected to the "
                                "GitHub Actions log where you can watch the check run in real time."
                            )
                        },
                        "annotations": {"color": "gray"},
                    }
                ]
            },
        },
    ]
}


def main() -> None:
    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"
    payload = json.dumps(BLOCKS).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())

    added = len(body.get("results", []))
    print(f"Done — added {added} block(s) to Finance Dashboard page ({PAGE_ID}).")
    print("Open Notion and scroll to the bottom of the page to see the new section.")


if __name__ == "__main__":
    main()
