"""
finance_email_check.py
======================
Reads Gmail for financial notification emails via IMAP and cross-checks
extracted dollar amounts against the Finta-synced Notion transactions
database.  Unmatched amounts are written as pages into a Finance Flags
database in Notion so they appear on the Finance Dashboard automatically.

No Google Cloud Console or OAuth setup required.  Uses a Gmail App Password,
which takes about two minutes to create:
    Gmail → Google Account → Security → 2-Step Verification → App Passwords

Environment variables
---------------------
NOTION_API_TOKEN                   — Notion integration secret
NOTION_FINANCE_TRANSACTIONS_DB_ID  — Finta-synced transactions database ID
NOTION_FINANCE_FLAGS_DB_ID         — Finance Flags database ID (created by
                                     setup_notion_finance_page.py)
GMAIL_ADDRESS                      — e.g. danirving1@gmail.com
GMAIL_APP_PASSWORD                 — 16-character app password from Gmail settings
FINANCE_EMAIL_LOOKBACK_DAYS        — (optional) days to look back, default 30
"""

import datetime as _dt
import email as _email
import email.header as _header
import email.utils as _eutils
import imaplib
import os
import re
from typing import Dict, List, Optional, Tuple

from notion_client import Client as NotionClient


AMOUNT_RE = re.compile(r'\$\s*([\d,]+(?:\.\d{2})?)')

_IMAP_SUBJECT_TERMS = [
    "transaction", "payment", "statement", "alert",
    "balance", "deposit", "withdrawal", "finta",
    "charge", "transfer", "confirmation",
]


def _get_env(name: str, *, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _decode_header(raw: str) -> str:
    parts = _header.decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


def _parse_email_date(date_str: str) -> str:
    """Convert an RFC 2822 email Date header to an ISO date string."""
    try:
        return _eutils.parsedate_to_datetime(date_str).date().isoformat()
    except Exception:
        return _dt.date.today().isoformat()


# ── GMAIL VIA IMAP ───────────────────────────────────────────────────────────

def fetch_financial_emails(
    gmail_address: str, app_password: str, lookback_days: int
) -> List[Dict]:
    cutoff_dt = _dt.date.today() - _dt.timedelta(days=lookback_days)
    since_str = cutoff_dt.strftime("%d-%b-%Y")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_address, app_password)
    mail.select("inbox", readonly=True)

    def _build_or_query(terms: List[str]) -> str:
        subjects = [f'SUBJECT "{t}"' for t in terms]
        while len(subjects) > 1:
            merged = []
            for i in range(0, len(subjects), 2):
                if i + 1 < len(subjects):
                    merged.append(f"OR ({subjects[i]}) ({subjects[i+1]})")
                else:
                    merged.append(subjects[i])
            subjects = merged
        return subjects[0]

    search_query = f'(SINCE "{since_str}" ({_build_or_query(_IMAP_SUBJECT_TERMS)}))'
    status, data = mail.search(None, search_query)
    if status != "OK" or not data[0]:
        mail.logout()
        return []

    msg_ids = data[0].split()[-150:]
    emails = []
    for mid in msg_ids:
        status, raw = mail.fetch(mid, "(RFC822)")
        if status != "OK":
            continue
        msg = _email.message_from_bytes(raw[0][1])
        subject = _decode_header(msg.get("Subject", ""))
        sender  = _decode_header(msg.get("From", ""))
        date    = msg.get("Date", "")
        body    = _get_text_body(msg)
        amounts = AMOUNT_RE.findall(subject + " " + body)
        emails.append({
            "from":    sender,
            "subject": subject,
            "date":    date,
            "amounts": list(dict.fromkeys(amounts)),
        })

    mail.logout()
    return emails


# ── NOTION READ ──────────────────────────────────────────────────────────────

def fetch_notion_amounts(
    notion: NotionClient, db_id: str, lookback_days: int
) -> List[float]:
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    amounts: List[float] = []
    cursor = None

    while True:
        params = {
            "database_id": db_id,
            "filter": {"property": "Date", "date": {"on_or_after": cutoff}},
        }
        if cursor:
            params["start_cursor"] = cursor
        resp = notion.databases.query(**params)

        for page in resp.get("results", []):
            props = page.get("properties", {})
            amt_prop = props.get("Amount") or props.get("amount")
            if amt_prop and amt_prop.get("type") == "number":
                val = amt_prop.get("number")
                if val is not None:
                    amounts.append(abs(float(val)))

        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    return amounts


# ── CROSS-CHECK ──────────────────────────────────────────────────────────────

def compute_unmatched(
    emails: List[Dict], notion_amounts: List[float]
) -> List[Dict]:
    """Return deduplicated list of {email, amount} dicts missing from Notion."""
    unmatched = []
    seen: set = set()
    for em in emails:
        for amt_str in em["amounts"]:
            try:
                amt = float(amt_str.replace(",", ""))
            except ValueError:
                continue
            if amt < 1.00:
                continue
            if any(abs(n - amt) < 0.02 for n in notion_amounts):
                continue
            key = (amt, em["subject"][:40])
            if key in seen:
                continue
            seen.add(key)
            unmatched.append({"email": em, "amount": amt})
    return unmatched


def print_report(
    emails: List[Dict],
    notion_amounts: List[float],
    unmatched: List[Dict],
    lookback_days: int,
) -> None:
    print("\n" + "=" * 66)
    print("  FINANCE EMAIL × NOTION CROSS-CHECK")
    print(f"  Period : last {lookback_days} days  |  {_dt.date.today().isoformat()}")
    print("=" * 66)
    print(f"\n  Financial emails found in Gmail : {len(emails)}")
    print(f"  Transactions found in Notion    : {len(notion_amounts)}\n")

    if not unmatched:
        print("  OK — no discrepancies. Gmail amounts align with Notion.\n")
    else:
        print(f"  WARNING — {len(unmatched)} amount(s) in email missing from Notion:\n")
        for item in unmatched:
            print(f"  ${item['amount']:>10,.2f}  |  {item['email']['subject'][:55]}")
            print(f"               From : {item['email']['from'][:55]}")
            print(f"               Date : {item['email']['date'][:30]}\n")

    print("=" * 66)
    if emails:
        print("\n  All financial emails scanned:\n")
        for e in emails:
            amts = "  ".join(f"${a}" for a in e["amounts"][:4]) or "(no $ found)"
            print(f"  {e['date'][:20]:22}  {e['subject'][:50]}")
            print(f"  {'':22}  {e['from'][:50]}")
            print(f"  {'':22}  Amounts: {amts}\n")


# ── NOTION WRITE-BACK ────────────────────────────────────────────────────────

def write_flags_to_notion(
    unmatched: List[Dict], notion: NotionClient, flags_db_id: str
) -> int:
    """
    For each unmatched item, create a page in the Finance Flags database
    unless an open flag for the same amount already exists.
    Returns the count of new pages created.
    """
    created = 0
    today = _dt.date.today().isoformat()

    for item in unmatched:
        amt = item["amount"]
        subject = item["email"]["subject"][:100]

        # Skip if an open flag for this amount already exists
        existing = notion.databases.query(
            database_id=flags_db_id,
            filter={
                "and": [
                    {"property": "Amount", "number": {"equals": amt}},
                    {"property": "Status", "select": {"does_not_equal": "Resolved"}},
                    {"property": "Status", "select": {"does_not_equal": "False Positive"}},
                ]
            },
            page_size=1,
        )
        if existing.get("results"):
            continue

        email_date = _parse_email_date(item["email"]["date"])
        notion.pages.create(
            parent={"database_id": flags_db_id},
            properties={
                "Email Subject": {
                    "title": [{"text": {"content": subject}}]
                },
                "Amount":       {"number": amt},
                "Sender":       {"rich_text": [{"text": {"content": item["email"]["from"][:200]}}]},
                "Email Date":   {"date": {"start": email_date}},
                "Flagged On":   {"date": {"start": today}},
                "Status":       {"select": {"name": "Needs Review"}},
            },
        )
        created += 1

    return created


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    notion_token    = _get_env("NOTION_API_TOKEN")
    transactions_db = _get_env("NOTION_FINANCE_TRANSACTIONS_DB_ID")
    flags_db_id     = os.getenv("NOTION_FINANCE_FLAGS_DB_ID")
    gmail_address   = _get_env("GMAIL_ADDRESS")
    app_password    = _get_env("GMAIL_APP_PASSWORD")
    lookback_days   = int(os.getenv("FINANCE_EMAIL_LOOKBACK_DAYS", "30"))

    print(f"Connecting to Gmail ({gmail_address}) via IMAP...")
    emails = fetch_financial_emails(gmail_address, app_password, lookback_days)
    print(f"  Found {len(emails)} financial email(s).")

    print("Querying Notion transactions...")
    notion  = NotionClient(auth=notion_token)
    amounts = fetch_notion_amounts(notion, transactions_db, lookback_days)
    print(f"  Found {len(amounts)} transaction(s) in Notion.")

    unmatched = compute_unmatched(emails, amounts)
    print_report(emails, amounts, unmatched, lookback_days)

    if flags_db_id:
        if unmatched:
            print(f"\nWriting flags to Notion ({flags_db_id})...")
            n = write_flags_to_notion(unmatched, notion, flags_db_id)
            print(f"  Created {n} new flag(s).  ({len(unmatched) - n} already tracked.)")
        else:
            print("\nNothing to flag — Notion is up to date.")
    else:
        print(
            "\nTip: set NOTION_FINANCE_FLAGS_DB_ID to auto-create flags in Notion.\n"
            "     Run the setup-notion-finance-page workflow to create the database."
        )


if __name__ == "__main__":
    main()
