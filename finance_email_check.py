"""
finance_email_check.py
======================
Reads Gmail for financial notification emails and cross-checks them against
the Finta-synced Notion transactions database.  Prints a plain-text
discrepancy report: any dollar amount found in a financial email that has no
matching transaction in Notion is flagged, so sync gaps surface immediately.

Setup
-----
1.  Enable the Gmail API in Google Cloud Console for your project.
2.  Download an OAuth 2.0 client ID (Desktop app type) as ``credentials.json``
    and place it in this directory.
3.  Run the script once locally — it opens a browser to authorize your Gmail
    account and stores ``token.json`` for subsequent headless runs.
4.  For CI/GitHub Actions, set ``GOOGLE_OAUTH_TOKEN_JSON`` to the contents of
    ``token.json`` (stored as a GitHub secret).

Environment variables
---------------------
NOTION_API_TOKEN                   — Notion integration secret
NOTION_FINANCE_TRANSACTIONS_DB_ID  — Finta-synced transactions database ID
GOOGLE_OAUTH_TOKEN_JSON            — (optional) token.json contents for headless runs
FINANCE_EMAIL_LOOKBACK_DAYS        — (optional) days to look back, default 30
"""

import base64
import datetime as _dt
import json
import os
import re
from typing import Any, Dict, List, Optional

from notion_client import Client as NotionClient
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
AMOUNT_RE = re.compile(r'\$\s*([\d,]+(?:\.\d{2})?)')

# Keywords used to narrow Gmail search to financial senders
_GMAIL_QUERY_TERMS = (
    "subject:transaction OR subject:payment OR subject:statement OR "
    "subject:alert OR subject:finta OR subject:balance OR subject:deposit OR "
    "subject:withdrawal"
)


def _get_env(name: str, *, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# ── GMAIL ────────────────────────────────────────────────────────────────────

def _build_gmail_service():
    """Authenticate with Gmail via OAuth 2.0 and return a service client."""
    creds = None
    token_str = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
    if token_str:
        creds = Credentials.from_authorized_user_info(json.loads(token_str), SCOPES)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise RuntimeError(
                    "credentials.json not found.\n"
                    "Download an OAuth 2.0 Desktop client ID from Google Cloud Console\n"
                    "and save it as credentials.json in this directory, then re-run."
                )
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: Dict) -> str:
    """Recursively extract plain-text content from a Gmail message payload."""
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if part.get("parts"):
            result = _decode_body(part)
            if result:
                return result
    # Fall back to top-level body (non-multipart messages)
    data = payload.get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace") if data else ""


def fetch_financial_emails(service, lookback_days: int) -> List[Dict]:
    """Return financial notification emails from the last ``lookback_days`` days."""
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    query = f"after:{cutoff} ({_GMAIL_QUERY_TERMS})"

    resp = service.users().messages().list(
        userId="me", q=query, maxResults=200
    ).execute()
    msg_refs = resp.get("messages", [])

    emails = []
    for ref in msg_refs:
        meta = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        sender  = headers.get("From", "")
        date    = headers.get("Date", "")

        body = _decode_body(meta.get("payload", {}))
        if not body:
            # Fetch full message only when metadata didn't include body
            full = service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            body = _decode_body(full.get("payload", {}))

        amounts = AMOUNT_RE.findall(subject + " " + body)
        emails.append({
            "id":      ref["id"],
            "from":    sender,
            "subject": subject,
            "date":    date,
            "amounts": list(dict.fromkeys(amounts)),  # deduplicate, preserve order
        })

    return emails


# ── NOTION ───────────────────────────────────────────────────────────────────

def fetch_notion_transactions(notion: NotionClient, db_id: str, lookback_days: int) -> List[float]:
    """Return unique absolute transaction amounts from Notion for the lookback period."""
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    amounts: List[float] = []
    cursor = None

    while True:
        params: Dict[str, Any] = {
            "database_id": db_id,
            "filter": {"property": "Date", "date": {"on_or_after": cutoff}},
        }
        if cursor:
            params["start_cursor"] = cursor
        resp = notion.databases.query(**params)

        for page in resp.get("results", []):
            props = page.get("properties", {})
            # Try "Amount" or "amount" property
            amt_prop = props.get("Amount") or props.get("amount")
            if amt_prop and amt_prop.get("type") == "number":
                val = amt_prop.get("number")
                if val is not None:
                    amounts.append(abs(float(val)))

        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    return amounts


# ── REPORT ───────────────────────────────────────────────────────────────────

def run_cross_check(emails: List[Dict], notion_amounts: List[float], lookback_days: int) -> None:
    """Compare Gmail financial emails against Notion transactions; print report."""
    print("\n" + "=" * 64)
    print("  FINANCE EMAIL CROSS-CHECK REPORT")
    print(f"  Period : last {lookback_days} days  |  {_dt.date.today().isoformat()}")
    print("=" * 64)
    print(f"\n  Gmail financial emails :  {len(emails)}")
    print(f"  Notion transactions    :  {len(notion_amounts)}\n")

    unmatched = []
    for email in emails:
        for amt_str in email["amounts"]:
            try:
                amt = float(amt_str.replace(",", ""))
            except ValueError:
                continue
            if amt < 1.00:          # ignore tiny amounts (fees, rounding)
                continue
            if not any(abs(n - amt) < 0.02 for n in notion_amounts):
                unmatched.append({"email": email, "amount": amt})

    if not unmatched:
        print("  OK — no discrepancies detected.")
        print("  Gmail amounts and Notion transactions appear aligned.\n")
    else:
        print(f"  WARNING — {len(unmatched)} amount(s) in email have no Notion match:\n")
        seen = set()
        for item in unmatched:
            key = (item["amount"], item["email"]["subject"][:40])
            if key in seen:
                continue
            seen.add(key)
            print(f"  ${item['amount']:>10,.2f}  |  {item['email']['subject'][:55]}")
            print(f"               From : {item['email']['from']}")
            print(f"               Date : {item['email']['date'][:25]}\n")

    print("=" * 64)
    print("\n  All financial emails scanned:\n")
    for e in emails:
        amts = "  ".join(f"${a}" for a in e["amounts"][:4]) or "(no amounts)"
        print(f"  {e['date'][:16]:18}  {e['subject'][:52]}")
        print(f"  {'':18}  From: {e['from'][:45]}")
        print(f"  {'':18}  Amounts: {amts}\n")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    notion_token     = _get_env("NOTION_API_TOKEN")
    transactions_db  = _get_env("NOTION_FINANCE_TRANSACTIONS_DB_ID")
    lookback_days    = int(os.getenv("FINANCE_EMAIL_LOOKBACK_DAYS", "30"))

    print("Connecting to Gmail...")
    gmail  = _build_gmail_service()
    emails = fetch_financial_emails(gmail, lookback_days)
    print(f"  Found {len(emails)} financial email(s).")

    print("Querying Notion transactions...")
    notion  = NotionClient(auth=notion_token)
    amounts = fetch_notion_transactions(notion, transactions_db, lookback_days)
    print(f"  Found {len(amounts)} transaction(s) in Notion.")

    run_cross_check(emails, amounts, lookback_days)


if __name__ == "__main__":
    main()
