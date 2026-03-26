"""Auto-configure persisted FreeCAD command from probe results."""

import json

from config_manager import set_freecad_python_cmd
from freecad_env_probe import run_probe


def auto_configure() -> dict:
    probe = run_probe()
    recommended = probe.get("recommended_freecad_python_cmd")

    if not recommended:
        return {
            "ok": False,
            "message": "No FreeCAD-capable command detected.",
            "probe": probe,
        }

    cfg = set_freecad_python_cmd(recommended)
    return {
        "ok": True,
        "message": f"Configured FreeCAD command: {recommended}",
        "config": cfg,
        "probe": probe,
    }


def main() -> None:
    print(json.dumps(auto_configure(), indent=2))


if __name__ == "__main__":
    main()
