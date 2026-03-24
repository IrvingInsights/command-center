"""
PeakHinge cassette corner + hinge + bearing interface generator.
Creates a simplified cassette volume, hinge axis, compression block, and bearing plate.
"""

import json
from pathlib import Path

PARAM_PATH = Path("params/cassette_corner_v1.json")


def load_params(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    p = load_params(PARAM_PATH)
    print("Loaded cassette corner parameters:")
    for k, v in p.items():
        print(f"{k}: {v}")

    # FreeCAD geometry generation goes here.
    # Suggested first pass:
    # 1. Create cassette box volume
    # 2. Create hinge axis body
    # 3. Add bearing plate body
    # 4. Add compression block body
    # 5. Save and export

    print("TODO: implement FreeCAD geometry for cassette interface.")


if __name__ == "__main__":
    main()
