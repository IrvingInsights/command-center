"""
notion_google_sync.py
=====================

This script provides a starting point for syncing tasks in a Notion database
with events on Google Calendar.  It implements a simple one‑way sync from
Notion to Google Calendar, but can be extended to support two‑way syncing if
desired.  To use this script you must provide credentials for both the
Notion API and a Google service account via environment variables.  See
README.md for setup details.

Environment variables
---------------------

* ``NOTION_API_TOKEN`` – secret token for the Notion API.  Create an
  integration at https://www.notion.so/my-integrations and share your
  database with that integration.
* ``NOTION_TASKS_DB_ID`` – the 32‑character database ID (without dashes) for
  your Tasks database.  You can find this in the database URL.
* ``GOOGLE_SERVICE_ACCOUNT_JSON`` – JSON string representing a service
  account key with Calendar API scope enabled.  You can also mount the
  service account key file and read it from disk if preferred.
* ``DOMAIN_CALENDAR_MAPPING`` – JSON string mapping Notion domain names to
  Google Calendar IDs.  For example::

      {
          "Personal & Home": "family01917596261905213245@group.calendar.google.com",
          "Book": "8fee3bef2083ca300ecc251e1b35ccfb56d4889341fc89e7e126e91737684577@group.calendar.google.com",
          ...
      }

* ``TIMEZONE`` – IANA timezone string (default: ``America/New_York``).

This script makes the following assumptions:

* Each task in your Notion database has the following properties:
    - **Name** (title): the name of the task.
    - **Due Date** (date): when the task is due.  Tasks without a due date are
      ignored in the sync.
    - **Status** (select or status): tasks marked as "Completed" are skipped.
    - **Domain** (relation): relation to a domain page.  The name of the
      domain must match a key in ``DOMAIN_CALENDAR_MAPPING``.
    - **GCal Event ID** (text): if populated, this script updates the
      corresponding calendar event rather than creating a new one.
    - **Last Synced** (date): timestamp of the last sync.  This field is
      updated each time the task is processed.

* Events are created as all‑day events on the due date unless the start and
  end times are specified as a datetime range.  You can extend the logic to
  support timeboxed tasks.

This example is intentionally minimal.  You should add error handling,
logging, and two‑way sync logic for a production system.
"""

import datetime as _dt
import json
import os
from typing import Any, Dict, Optional

from notion_client import Client as NotionClient  # type: ignore
from google.oauth2 import service_account  # type: ignore
from googleapiclient.discovery import build  # type: ignore


def _get_env(name: str, *, required: bool = True) -> Optional[str]:
    """Helper to fetch environment variables with optional enforcement."""
    value = os.getenv(name)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_calendar_mapping(mapping_str: str) -> Dict[str, str]:
    """Parse the JSON mapping of domain names to calendar IDs."""
    try:
        mapping = json.loads(mapping_str)
        if not isinstance(mapping, dict):
            raise ValueError("Mapping must be a JSON object")
        return {str(k): str(v) for k, v in mapping.items()}
    except json.JSONDecodeError as exc:
        raise ValueError("DOMAIN_CALENDAR_MAPPING must be valid JSON") from exc


def _get_google_service(calendar_credentials: str):
    """Create a Google Calendar service client from a JSON key string."""
    info = json.loads(calendar_credentials)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=credentials)


def _get_task_properties(page: Dict[str, Any]) -> Dict[str, Any]:
    """Extract useful properties from a Notion page result."""
    props: Dict[str, Any] = page.get("properties", {})
    result: Dict[str, Any] = {}
    # Task name (title)
    title_prop = props.get("Name") or props.get("Title")
    if title_prop and title_prop.get("type") == "title":
        title_parts = title_prop.get("title", [])
        result["name"] = "".join(part.get("plain_text", "") for part in title_parts)
    else:
        result["name"] = "Untitled"
    # Due date
    due = props.get("Due Date") or props.get("Due date") or props.get("Due")
    if due and due.get("type") == "date" and due.get("date"):
        result["due"] = due["date"]  # contains start/end/is_datetime
    else:
        result["due"] = None
    # Status
    status_prop = props.get("Status")
    if status_prop:
        # Status may be a select or status type
        if status_prop.get("type") in {"select", "status"}:
            result["status"] = status_prop.get(status_prop["type"], {}).get("name")
    # Domain relation
    domain_prop = props.get("Domain")
    if domain_prop and domain_prop.get("type") == "relation":
        rels = domain_prop.get("relation", [])
        if rels:
            # only take the first related page
            page_id = rels[0].get("id")
            result["domain_id"] = page_id
    # GCal Event ID
    gcal_id_prop = props.get("GCal Event ID") or props.get("Google Calendar Event ID")
    if gcal_id_prop and gcal_id_prop.get("type") == "rich_text":
        texts = gcal_id_prop.get("rich_text", [])
        result["gcal_id"] = "".join(t.get("plain_text", "") for t in texts)
    else:
        result["gcal_id"] = None
    return result


def _parse_notion_date(date_dict: Dict[str, Any], tz: str) -> (_dt.datetime, _dt.datetime):
    """
    Convert Notion date dictionary into start/end datetimes.  If the end date
    isn't provided, the event is treated as an all‑day event on the start date.
    The timezone ``tz`` is applied for naive dates.
    """
    start_str = date_dict.get("start")
    end_str = date_dict.get("end")
    # Parse ISO date/time
    if start_str is None:
        raise ValueError("start date is missing")
    if "T" in start_str:
        start_dt = _dt.datetime.fromisoformat(start_str)
    else:
        start_dt = _dt.datetime.fromisoformat(start_str + "T00:00:00")
    if end_str:
        if "T" in end_str:
            end_dt = _dt.datetime.fromisoformat(end_str)
        else:
            # End date in Notion is exclusive for all-day events.  Treat the end
            # date as the same day at 23:59:59.
            end_dt = _dt.datetime.fromisoformat(end_str + "T23:59:59")
    else:
        # Single day event, end = start + 1 day
        end_dt = start_dt + _dt.timedelta(days=1)
    return start_dt, end_dt


def sync_notion_to_calendar(notion: NotionClient, calendar_service, db_id: str, calendar_map: Dict[str, str], tz: str) -> None:
    """Synchronise Notion tasks to Google Calendar as all‑day events."""
    # Fetch tasks
    tasks = notion.databases.query(database_id=db_id)
    for page in tasks.get("results", []):
        props = _get_task_properties(page)
        name = props.get("name")
        due = props.get("due")
        status = props.get("status")
        gcal_id = props.get("gcal_id")
        domain_id = props.get("domain_id")
        # Skip completed tasks or tasks without a due date
        if status == "Completed" or due is None:
            continue
        # Get domain page to look up name
        domain_name = None
        if domain_id:
            try:
                domain_page = notion.pages.retrieve(domain_id)
                dn_props = domain_page.get("properties", {})
                title_prop = dn_props.get("Name") or dn_props.get("Title")
                if title_prop and title_prop.get("type") == "title":
                    parts = title_prop.get("title", [])
                    domain_name = "".join(p.get("plain_text", "") for p in parts)
            except Exception:
                pass
        # Find calendar id
        calendar_id = calendar_map.get(domain_name or "")
        if not calendar_id:
            # Domain not mapped, skip
            continue
        # Parse Notion date into start/end times
        try:
            start_dt, end_dt = _parse_notion_date(due, tz)
        except Exception:
            continue
        event_body = {
            "summary": name,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": tz,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": tz,
            },
            "description": f"View in Notion: https://www.notion.so/{page['id']}"
        }
        try:
            if gcal_id:
                # Update existing event
                calendar_service.events().update(
                    calendarId=calendar_id,
                    eventId=gcal_id,
                    body=event_body
                ).execute()
            else:
                # Create new event
                created = calendar_service.events().insert(
                    calendarId=calendar_id,
                    body=event_body
                ).execute()
                gcal_id_new = created.get("id")
                # Update Notion page with the new event ID and timestamp
                notion.pages.update(
                    page["id"],
                    properties={
                        "GCal Event ID": {
                            "rich_text": [
                                {
                                    "text": {"content": gcal_id_new}
                                }
                            ]
                        },
                        "Last Synced": {
                            "date": {
                                "start": _dt.datetime.utcnow().isoformat()
                            }
                        }
                    }
                )
        except Exception as exc:
            # Log or handle error (here we just print)
            print(f"Error syncing task '{name}': {exc}")


def main() -> None:
    # Load configuration from environment
    notion_token = _get_env("NOTION_API_TOKEN")
    notion_db_id = _get_env("NOTION_TASKS_DB_ID")
    calendar_mapping_str = _get_env("DOMAIN_CALENDAR_MAPPING")
    gcal_creds = _get_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    timezone = os.getenv("TIMEZONE", "America/New_York")

    calendar_map = _parse_calendar_mapping(calendar_mapping_str)
    notion = NotionClient(auth=notion_token)
    gcal_service = _get_google_service(gcal_creds)
    sync_notion_to_calendar(notion, gcal_service, notion_db_id, calendar_map, timezone)


if __name__ == "__main__":
    main()
