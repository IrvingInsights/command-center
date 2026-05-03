"""
setup_notion_finance_page.py
============================
One-time setup script that:
  1. Adds the Finance Email Cross-Check section to the Finance Dashboard page
  2. Creates a "Finance Flags" database under that page and prints its ID

Run via GitHub Actions (see .github/workflows/setup-notion-finance-page.yml).
After the run, copy the printed database ID and save it as the GitHub secret
NOTION_FINANCE_FLAGS_DB_ID so the weekly check can write flags back to Notion.

Environment variables
---------------------
NOTION_API_TOKEN          — Notion integration secret
FINANCE_PAGE_ID           — Finance Dashboard page ID (without dashes)
FINANCE_TRIGGER_URL       — Full trigger URL for the "Run Now" link
"""

import json
import os
import urllib.request
import urllib.error

TOKEN   = os.environ["NOTION_API_TOKEN"]
PAGE_ID = os.environ.get("FINANCE_PAGE_ID", "24846ef5886245f78fef02152df823d6")
TRIGGER_URL = os.environ.get(
    "FINANCE_TRIGGER_URL",
    "https://irving-mvp.onrender.com/trigger-finance-check?token=irving2026",
)

NOTION_VERSION = "2022-06-28"


def _notion_request(method: str, path: str, body=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def add_trigger_section() -> int:
    """Append the trigger callout section to the Finance Dashboard page."""
    body = {
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
                            "text": {
                                "content": "▶  Run Finance Check Now",
                                "link": {"url": TRIGGER_URL},
                            },
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
    result = _notion_request("PATCH", f"/blocks/{PAGE_ID}/children", body)
    return len(result.get("results", []))


def create_flags_database() -> str:
    """
    Create a 'Finance Flags' database as a child of the Finance Dashboard page.
    Returns the new database ID.
    """
    body = {
        "parent": {"type": "page_id", "page_id": PAGE_ID},
        "icon": {"type": "emoji", "emoji": "⚠️"},
        "title": [{"type": "text", "text": {"content": "Finance Flags"}}],
        "properties": {
            "Email Subject": {"title": {}},
            "Amount": {"number": {"format": "dollar"}},
            "Sender": {"rich_text": {}},
            "Email Date": {"date": {}},
            "Flagged On": {"date": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Needs Review", "color": "red"},
                        {"name": "Resolved",     "color": "green"},
                        {"name": "False Positive", "color": "gray"},
                    ]
                }
            },
        },
    }
    result = _notion_request("POST", "/databases", body)
    return result["id"].replace("-", "")


def main() -> None:
    print(f"Adding trigger section to Finance Dashboard ({PAGE_ID})...")
    n_blocks = add_trigger_section()
    print(f"  Added {n_blocks} block(s).")

    print("\nCreating Finance Flags database...")
    flags_db_id = create_flags_database()
    print(f"  Done.\n")

    print("=" * 60)
    print("  NEXT STEP — save this as a GitHub Actions secret:")
    print()
    print(f"  Secret name : NOTION_FINANCE_FLAGS_DB_ID")
    print(f"  Secret value: {flags_db_id}")
    print("=" * 60)
    print()
    print("  Settings → Secrets and variables → Actions → New repository secret")
    print("  Then re-run the Finance Email Cross-Check workflow to verify.")


if __name__ == "__main__":
    main()
