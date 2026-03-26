"""Step 1 conversational runner for pipe pivot.

Usage:
  python scripts/step1_chat_runner.py --request \"set bore diameter to 65 mm\"
  python scripts/step1_chat_runner.py --revert-last
  python scripts/step1_chat_runner.py --save-last
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from contract_validation import assert_valid_edit_plan, assert_valid_edit_request
from drive_uploader import upload_directory_to_drive
from config_manager import get_freecad_python_cmd

ROOT = Path(__file__).resolve().parents[1]
PARAM_PATH = ROOT / "params" / "pipe_pivot_v1.json"
RUNTIME_DIR = ROOT / "runtime"
JOBS_DIR = RUNTIME_DIR / "jobs"
SAVED_DIR = RUNTIME_DIR / "saved"
HISTORY_PATH = RUNTIME_DIR / "history.jsonl"
BUILD_SCRIPT = ROOT / "scripts" / "build_pipe_pivot.py"

PARAM_ALIASES = {
    "bore diameter": "bore_diameter",
    "sleeve outer diameter": "sleeve_outer_diameter",
    "sleeve inner diameter": "sleeve_inner_diameter",
    "pipe outer diameter": "pipe_outer_diameter",
    "pipe inner diameter": "pipe_inner_diameter",
    "retention gap": "retention_gap",
    "edge distance": "edge_distance",
    "rib length": "rib_length",
    "rib height": "rib_height",
    "rib thickness": "rib_thickness",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run step-1 conversational edit for pipe pivot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request", help="Natural language request")
    group.add_argument("--revert-last", action="store_true", help="Revert params from the latest job")
    group.add_argument("--save-last", action="store_true", help="Save latest job artifacts as a named snapshot")
    group.add_argument("--save-last-drive", action="store_true", help="Save latest artifacts and upload snapshot zip to Google Drive")
    parser.add_argument("--strict-freecad", action="store_true", help="Require real FreeCAD build and fail otherwise")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def parse_request(request: str, params: dict) -> tuple[str, float]:
    lowered = request.lower().strip()
    value_match = re.search(r"(-?\d+(?:\.\d+)?)", lowered)
    if not value_match:
        raise ValueError("Couldn't find a numeric value in your request.")

    value = float(value_match.group(1))

    for phrase, key in PARAM_ALIASES.items():
        if phrase in lowered:
            if key not in params:
                raise ValueError(f"Mapped parameter '{key}' not present in params file.")
            return key, value

    raise ValueError(
        "Couldn't map that request to a supported parameter. Try phrases like 'bore diameter' or 'rib length'."
    )


def append_history(entry: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_latest_job_dir() -> Path:
    jobs = [p for p in JOBS_DIR.glob("job_*") if p.is_dir()]
    if not jobs:
        raise FileNotFoundError("No previous jobs found.")
    jobs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jobs[0]


def build_command_prefix() -> list[str]:
    cmd = os.getenv("FREECAD_PYTHON_CMD", "").strip()
    if not cmd:
        cfg_cmd = get_freecad_python_cmd()
        cmd = cfg_cmd or "python"
    return shlex.split(cmd)


def run_build_with_current_params() -> int:
    cmd = [*build_command_prefix(), str(BUILD_SCRIPT), "--params", str(PARAM_PATH)]
    result = subprocess.run(cmd, cwd=ROOT.parent, capture_output=True, text=True, check=False)
    return result.returncode


def revert_last() -> dict:
    latest_job_dir = get_latest_job_dir()
    params_before_path = latest_job_dir / "params_before.json"
    if not params_before_path.exists():
        raise FileNotFoundError(f"Missing params_before.json in {latest_job_dir}")

    original_params = load_json(params_before_path)
    write_json(PARAM_PATH, original_params)
    build_returncode = run_build_with_current_params()

    summary = {
        "job_id": f"revert_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        "status": "reverted" if build_returncode == 0 else "failed",
        "request_text": "revert last",
        "reverted_from_job": latest_job_dir.name,
        "job_dir": str(latest_job_dir.relative_to(ROOT)),
        "build_returncode": build_returncode,
    }
    append_history(summary)
    print(json.dumps(summary, indent=2))
    return summary


def save_last(upload_drive: bool = False) -> dict:
    latest_job_dir = get_latest_job_dir()
    SAVED_DIR.mkdir(parents=True, exist_ok=True)

    target_name = f"saved_{latest_job_dir.name}"
    target_dir = SAVED_DIR / target_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(latest_job_dir, target_dir)

    summary = {
        "job_id": f"save_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        "status": "saved",
        "request_text": "save last",
        "saved_from_job": latest_job_dir.name,
        "saved_dir": str(target_dir.relative_to(ROOT)),
    }

    if upload_drive:
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if not creds_json or not folder_id:
            raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_DRIVE_FOLDER_ID for Drive upload.")

        drive_meta = upload_directory_to_drive(
            target_dir,
            upload_name=f"{target_name}.zip",
            creds_json=creds_json,
            folder_id=folder_id,
        )
        summary["status"] = "saved_and_uploaded"
        summary.update(drive_meta)
    append_history(summary)
    print(json.dumps(summary, indent=2))
    return summary


def run_request(request_text: str, strict_freecad: bool = False) -> dict:
    job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    edit_request = {
        "request_text": request_text,
        "subassembly": "pipe_pivot",
        "timestamp_utc": now_iso,
        "user_id": "local_user",
    }
    assert_valid_edit_request(edit_request)
    write_json(job_dir / "edit_request.json", edit_request)

    params_before = load_json(PARAM_PATH)
    write_json(job_dir / "params_before.json", params_before)

    assumptions = []
    status = "applied"
    build_returncode = 0

    try:
        key, new_value = parse_request(request_text, params_before)
        old_value = params_before[key]

        params_after = dict(params_before)
        params_after[key] = new_value
        write_json(job_dir / "params_after.json", params_after)

        plan = {
            "subassembly": "pipe_pivot",
            "changes": [
                {
                    "parameter": key,
                    "old_value": old_value,
                    "new_value": new_value,
                    "unit": "mm",
                }
            ],
            "assumptions": assumptions,
            "status": status,
        }
        assert_valid_edit_plan(plan)
        write_json(job_dir / "edit_plan.json", plan)

        write_json(PARAM_PATH, params_after)

        build_artifacts_dir = job_dir / "build_artifacts"
        cmd = [
            *build_command_prefix(),
            str(BUILD_SCRIPT),
            "--params",
            str(PARAM_PATH),
            "--out-dir",
            str(build_artifacts_dir),
        ]
        if strict_freecad:
            cmd.append("--strict-freecad")
        result = subprocess.run(cmd, cwd=ROOT.parent, capture_output=True, text=True, check=False)
        build_returncode = result.returncode

        with (job_dir / "build.log").open("w", encoding="utf-8") as f:
            f.write("$ " + " ".join(cmd) + "\n\n")
            f.write(result.stdout)
            if result.stderr:
                f.write("\n[stderr]\n")
                f.write(result.stderr)

        if build_returncode != 0:
            status = "failed"
            plan["status"] = status
            assert_valid_edit_plan(plan)
            write_json(job_dir / "edit_plan.json", plan)

    except Exception as exc:
        status = "failed"
        plan = {
            "subassembly": "pipe_pivot",
            "changes": [],
            "assumptions": assumptions,
            "status": status,
            "error": str(exc),
        }
        assert_valid_edit_plan(plan)
        write_json(job_dir / "edit_plan.json", plan)
        with (job_dir / "build.log").open("w", encoding="utf-8") as f:
            f.write(f"Error: {exc}\n")

    summary = {
        "job_id": job_id,
        "status": status,
        "request_text": request_text,
        "job_dir": str(job_dir.relative_to(ROOT)),
        "build_returncode": build_returncode,
    }
    append_history(summary)

    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    args = parse_args()
    if args.revert_last:
        summary = revert_last()
    elif args.save_last:
        summary = save_last()
    elif args.save_last_drive:
        summary = save_last(upload_drive=True)
    else:
        summary = run_request(args.request.strip(), strict_freecad=args.strict_freecad)

    if summary.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
