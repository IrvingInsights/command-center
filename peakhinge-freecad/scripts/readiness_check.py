"""Readiness diagnostics for Step-1 conversational CAD app."""

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_pipe_pivot.py"
RUNTIME_DIRS = [ROOT / "runtime", ROOT / "runtime" / "jobs", ROOT / "runtime" / "saved"]


def _check_dependency(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def _check_build_script() -> dict:
    return {
        "path": str(BUILD_SCRIPT),
        "exists": BUILD_SCRIPT.exists(),
    }


def _ensure_runtime_dirs() -> list[dict]:
    results = []
    for path in RUNTIME_DIRS:
        try:
            path.mkdir(parents=True, exist_ok=True)
            results.append({"path": str(path), "ok": True})
        except Exception as exc:
            results.append({"path": str(path), "ok": False, "error": str(exc)})
    return results


def _check_optional_integrations() -> dict:
    return {
        "google_drive_env_present": bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") and os.getenv("GOOGLE_DRIVE_FOLDER_ID")),
        "google_auth_installed": _check_dependency("google.oauth2"),
        "google_api_client_installed": _check_dependency("googleapiclient.discovery"),
    }


def run_readiness_check() -> dict:
    build = _check_build_script()
    runtime_dirs = _ensure_runtime_dirs()
    runtime_ok = all(item["ok"] for item in runtime_dirs)

    dependencies = {
        "flask_installed": _check_dependency("flask"),
        "freecad_module_installed": _check_dependency("FreeCAD"),
        "part_module_installed": _check_dependency("Part"),
        "mesh_module_installed": _check_dependency("Mesh"),
    }

    optional = _check_optional_integrations()

    freecad_ready = dependencies["freecad_module_installed"] and dependencies["part_module_installed"] and dependencies["mesh_module_installed"]
    mvp_ready = build["exists"] and runtime_ok
    integration_ready = optional["google_drive_env_present"] and optional["google_auth_installed"] and optional["google_api_client_installed"]

    return {
        "ready": mvp_ready,
        "mvp_ready": mvp_ready,
        "strict_ready": freecad_ready,
        "freecad_ready": freecad_ready,
        "integration_ready": integration_ready,
        "build_script": build,
        "runtime_dirs": runtime_dirs,
        "dependencies": dependencies,
        "optional_integrations": optional,
    }


def main() -> None:
    print(json.dumps(run_readiness_check(), indent=2))


if __name__ == "__main__":
    main()
