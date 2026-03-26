"""Probe this environment for FreeCAD-capable Python execution paths."""

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_pipe_pivot.py"

COMMON_CANDIDATES = [
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\FreeCAD\FreeCAD 1.0.lnk",
    r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\FreeCAD.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCAD.exe",
    "/usr/bin/freecadcmd",
    "/usr/local/bin/freecadcmd",
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
]


def _candidate_commands() -> list[str]:
    candidates: list[str] = []
    env_cmd = os.getenv("FREECAD_PYTHON_CMD", "").strip()
    if env_cmd:
        candidates.append(env_cmd)

    for cmd_name in ["freecadcmd", "FreeCADCmd.exe", "FreeCAD.exe", "python"]:
        resolved = shutil.which(cmd_name)
        if resolved:
            candidates.append(resolved)

    candidates.extend(COMMON_CANDIDATES)

    seen = set()
    unique: list[str] = []
    for item in candidates:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _probe_command(cmd: str) -> dict:
    command = [cmd, str(BUILD_SCRIPT), "--probe"] if "python" in Path(cmd).name.lower() else [cmd, "--version"]
    try:
        result = subprocess.run(command, cwd=ROOT.parent, capture_output=True, text=True, check=False, timeout=12)
        ok = result.returncode == 0
        return {
            "command": cmd,
            "ok": ok,
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[:1000],
            "stderr": (result.stderr or "")[:1000],
        }
    except Exception as exc:
        return {"command": cmd, "ok": False, "error": str(exc)}


def run_probe(custom_candidates: list[str] | None = None) -> dict:
    candidates = _candidate_commands()
    if custom_candidates:
        for item in custom_candidates:
            if item not in candidates:
                candidates.insert(0, item)

    results = [_probe_command(cmd) for cmd in candidates]
    recommended = None
    for item in results:
        if item.get("ok"):
            recommended = item["command"]
            break

    summary = {
        "platform": platform.platform(),
        "cwd": str(ROOT.parent),
        "build_script": str(BUILD_SCRIPT),
        "candidates": candidates,
        "results": results,
        "recommended_freecad_python_cmd": recommended,
    }
    return summary


def main() -> None:
    print(json.dumps(run_probe(), indent=2))


if __name__ == "__main__":
    main()
