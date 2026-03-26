"""Workable Step-1 conversational runner for pipe pivot.

This version edits params/pipe_pivot_v1.json directly, invokes FreeCADCmd
using the same execution pattern that already worked locally, and records
job history/artifacts under runtime/jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PARAM_PATH = ROOT / "params" / "pipe_pivot_v1.json"
SCRIPT_PATH = ROOT / "scripts" / "build_pipe_pivot_v1.py"
MODELS_DIR = ROOT / "models"
STEP_DIR = ROOT / "exports" / "step"
STL_DIR = ROOT / "exports" / "stl"
RUNTIME_DIR = ROOT / "runtime"
JOBS_DIR = RUNTIME_DIR / "jobs"
HISTORY_PATH = RUNTIME_DIR / "history.jsonl"

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
    "washer outer diameter": "washer_outer_diameter",
    "washer inner diameter": "washer_inner_diameter",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Step-1 conversational edit for pipe pivot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request", help="Natural language request like: set bore diameter to 65 mm")
    group.add_argument("--revert-last", action="store_true")
    parser.add_argument("--strict-freecad", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def append_history(entry: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def find_freecad_cmd() -> str | None:
    candidates = [
        os.getenv("FREECAD_CMD", "").strip(),
        r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
        r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe",
        r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
        shutil.which("FreeCADCmd.exe") or "",
        shutil.which("freecadcmd") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def parse_request(request: str, params: dict) -> tuple[str, float]:
    lowered = request.lower().strip()
    value_match = re.search(r"(-?\d+(?:\.\d+)?)", lowered)
    if not value_match:
        raise ValueError("Could not find a numeric value in the request.")
    new_value = float(value_match.group(1))

    for phrase, key in PARAM_ALIASES.items():
        if phrase in lowered:
            if key not in params:
                raise ValueError(f"Mapped parameter '{key}' not present in params file.")
            return key, new_value
    raise ValueError("Could not map request to a supported parameter.")


def get_latest_job_dir() -> Path:
    jobs = [p for p in JOBS_DIR.glob("job_*") if p.is_dir()]
    if not jobs:
        raise FileNotFoundError("No previous jobs found.")
    jobs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jobs[0]


def build_via_freecad(strict_freecad: bool) -> tuple[int, str, str]:
    freecad_cmd = find_freecad_cmd()
    if not freecad_cmd:
        if strict_freecad:
            return 1, "", "FreeCADCmd was not found."
        return 0, "Skipped strict FreeCAD build because FreeCADCmd was not found.", ""

    escaped_script = str(SCRIPT_PATH).replace('\\', '\\\\')
    python_command = (
        "import os; p=r'" + escaped_script + "'; "
        "os.chdir(os.path.dirname(p)); "
        "g={'__name__':'__main__','__file__':p}; "
        "exec(open(p,'r',encoding='utf-8').read(), g)"
    )
    result = subprocess.run([freecad_cmd, "-c", python_command], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def collect_outputs(job_dir: Path) -> dict:
    artifacts_dir = job_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    mapping = {
        "fcstd": MODELS_DIR / "pipe_pivot_v1.FCStd",
        "step": STEP_DIR / "pipe_pivot_v1.step",
        "stl": STL_DIR / "pipe_pivot_v1.stl",
    }
    for key, source in mapping.items():
        exists = source.exists()
        target = artifacts_dir / source.name
        if exists:
            shutil.copy2(source, target)
            outputs[key] = str(target.relative_to(ROOT))
        else:
            outputs[key] = None
    return outputs


def revert_last(strict_freecad: bool) -> dict:
    latest_job = get_latest_job_dir()
    original = load_json(latest_job / "params_before.json")
    write_json(PARAM_PATH, original)
    code, stdout, stderr = build_via_freecad(strict_freecad)
    summary = {
        "status": "reverted" if code == 0 else "failed",
        "reverted_from": latest_job.name,
        "build_returncode": code,
        "stdout_tail": stdout[-1000:],
        "stderr_tail": stderr[-1000:],
    }
    append_history(summary)
    return summary


def run_request(request_text: str, strict_freecad: bool) -> dict:
    params_before = load_json(PARAM_PATH)
    key, new_value = parse_request(request_text, params_before)
    old_value = params_before[key]

    params_after = dict(params_before)
    params_after[key] = new_value

    job_id = f"job_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    write_json(job_dir / "params_before.json", params_before)
    write_json(job_dir / "params_after.json", params_after)
    write_json(PARAM_PATH, params_after)

    code, stdout, stderr = build_via_freecad(strict_freecad)
    outputs = collect_outputs(job_dir)

    with (job_dir / "build.log").open("w", encoding="utf-8") as f:
        f.write(stdout)
        if stderr:
            f.write("\n[stderr]\n")
            f.write(stderr)

    summary = {
        "job_id": job_id,
        "status": "ok" if code == 0 else "failed",
        "subassembly": "pipe_pivot",
        "request_text": request_text,
        "change": {
            "parameter": key,
            "old_value": old_value,
            "new_value": new_value,
            "unit": "mm",
        },
        "job_dir": str(job_dir.relative_to(ROOT)),
        "build_returncode": code,
        "outputs": outputs,
        "stdout_tail": stdout[-1000:],
        "stderr_tail": stderr[-1000:],
    }
    write_json(job_dir / "summary.json", summary)
    append_history(summary)
    return summary


def main() -> None:
    args = parse_args()
    if args.revert_last:
        summary = revert_last(args.strict_freecad)
    else:
        summary = run_request(args.request.strip(), args.strict_freecad)
    print(json.dumps(summary, indent=2))
    if summary.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
