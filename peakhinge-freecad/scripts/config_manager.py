"""Runtime config helpers for Step-1 app."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "runtime" / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def set_freecad_python_cmd(cmd: str) -> dict:
    cfg = load_config()
    cfg["freecad_python_cmd"] = cmd
    save_config(cfg)
    return cfg


def get_freecad_python_cmd() -> str | None:
    cfg = load_config()
    value = cfg.get("freecad_python_cmd")
    return value if isinstance(value, str) and value.strip() else None
