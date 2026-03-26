"""Google Drive upload helper for saved iteration artifacts.

Requires environment variables:
- GOOGLE_SERVICE_ACCOUNT_JSON  (service account JSON string)
- GOOGLE_DRIVE_FOLDER_ID       (target folder id)
"""

import io
import json
import tempfile
import zipfile
from pathlib import Path


def _build_zip_bytes(source_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir))
    return buf.getvalue()


def upload_directory_to_drive(source_dir: Path, upload_name: str, creds_json: str, folder_id: str) -> dict:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive dependencies are missing. Install google-api-python-client and google-auth."
        ) from exc

    creds_info = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
    service = build("drive", "v3", credentials=credentials)

    zip_bytes = _build_zip_bytes(source_dir)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(zip_bytes)
        tmp_path = Path(tmp.name)

    file_metadata = {"name": upload_name, "parents": [folder_id]}
    media = MediaFileUpload(str(tmp_path), mimetype="application/zip")
    created = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,name,webViewLink,webContentLink",
    ).execute()

    return {
        "drive_file_id": created.get("id"),
        "drive_name": created.get("name"),
        "drive_web_view_link": created.get("webViewLink"),
        "drive_download_link": created.get("webContentLink"),
    }
