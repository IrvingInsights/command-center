"""
finance_email_check.py
======================
Reads Gmail for financial notification emails via IMAP and cross-checks
extracted dollar amounts against the Finta-synced Notion transactions
database.  Prints a plain-text discrepancy report so sync gaps surface
without manual review.

No Google Cloud Console or OAuth setup required.  Uses a Gmail App Password,
which takes about two minutes to create:
    Gmail → Google Account → Security → 2-Step Verification → App Passwords

Environment variables
---------------------
NOTION_API_TOKEN                   — Notion integration secret
NOTION_FINANCE_TRANSACTIONS_DB_ID  — Finta-synced transactions database ID
GMAIL_ADDRESS                      — e.g. danirving1@gmail.com
GMAIL_APP_PASSWORD                 — 16-character app password from Gmail settings
FINANCE_EMAIL_LOOKBACK_DAYS        — (optional) days to look back, default 30
"""

import datetime as _dt
import email as _email
import email.header as _header
import imaplib
import os
import re
from typing import Dict, List, Optional, Tuple

from notion_client import Client as NotionClient


AMOUNT_RE = re.compile(r'\$\s*([\d,]+(?:\.\d{2})?)')

# IMAP search terms — OR'd together so we catch any financial email type
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
    """Decode a potentially encoded email header value to plain text."""
    parts = _header.decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_text_body(msg) -> str:
    """Extract plain-text body from an email.Message object."""
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


# ── GMAIL VIA IMAP ───────────────────────────────────────────────────────────

def fetch_financial_emails(
    gmail_address: str, app_password: str, lookback_days: int
) -> List[Dict]:
    """
    Connect to Gmail via IMAP and return financial notification emails
    from the last ``lookback_days`` days.
    """
    cutoff_dt = _dt.date.today() - _dt.timedelta(days=lookback_days)
    # IMAP date format: DD-Mon-YYYY
    since_str = cutoff_dt.strftime("%d-%b-%Y")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_address, app_password)
    mail.select("inbox", readonly=True)

    # Build an IMAP OR search across all subject keywords
    # IMAP OR is binary: OR (SUBJECT "a") (OR (SUBJECT "b") (SUBJECT "c")) ...
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

    msg_ids = data[0].split()
    # Limit to 150 most-recent to avoid slow runs on large inboxes
    msg_ids = msg_ids[-150:]

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
            "amounts": list(dict.fromkeys(amounts)),  # deduplicated, order-preserved
        })

    mail.logout()
    return emails


# ── NOTION ───────────────────────────────────────────────────────────────────

def fetch_notion_amounts(
    notion: NotionClient, db_id: str, lookback_days: int
) -> List[float]:
    """Return absolute transaction amounts from Notion for the lookback period."""
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


# ── REPORT ───────────────────────────────────────────────────────────────────

def run_cross_check(
    emails: List[Dict], notion_amounts: List[float], lookback_days: int
) -> None:
    """Flag email amounts that have no matching Notion transaction."""
    print("\n" + "=" * 66)
    print("  FINANCE EMAIL × NOTION CROSS-CHECK")
    print(f"  Period : last {lookback_days} days  |  {_dt.date.today().isoformat()}")
    print("=" * 66)
    print(f"\n  Financial emails found in Gmail : {len(emails)}")
    print(f"  Transactions found in Notion    : {len(notion_amounts)}\n")

    unmatched = []
    for em in emails:
        for amt_str in em["amounts"]:
            try:
                amt = float(amt_str.replace(",", ""))
            except ValueError:
                continue
            if amt < 1.00:
                continue
            if not any(abs(n - amt) < 0.02 for n in notion_amounts):
                unmatched.append({"email": em, "amount": amt})

    if not unmatched:
        print("  OK — no discrepancies. Gmail amounts align with Notion.\n")
    else:
        # Deduplicate by (amount, subject prefix)
        seen: set = set()
        unique = []
        for item in unmatched:
            key = (item["amount"], item["email"]["subject"][:40])
            if key not in seen:
                seen.add(key)
                unique.append(item)

        print(f"  WARNING — {len(unique)} amount(s) in email missing from Notion:\n")
        for item in unique:
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


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    notion_token    = _get_env("NOTION_API_TOKEN")
    transactions_db = _get_env("NOTION_FINANCE_TRANSACTIONS_DB_ID")
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

    run_cross_check(emails, amounts, lookback_days)


if __name__ == "__main__":
    main()
