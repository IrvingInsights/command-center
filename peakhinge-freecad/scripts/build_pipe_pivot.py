"""
PeakHinge pipe-through-bore pivot generator.
Early-stage geometry only.
Creates a rib, bore, sleeve, pivot pipe, and washer reference parts.
"""

import json
from pathlib import Path

PARAM_PATH = Path("params/pipe_pivot_v1.json")


def load_params(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    p = load_params(PARAM_PATH)
    print("Loaded parameters:")
    for k, v in p.items():
        print(f"{k}: {v}")

    # FreeCAD geometry generation goes here.
    # Suggested first pass:
    # 1. Create rib block
    # 2. Cut cylindrical bore
    # 3. Create sleeve solid
    # 4. Create pivot pipe solid
    # 5. Create washer/end-stop variants
    # 6. Save FCStd
    # 7. Export STEP/STL

    print("TODO: implement FreeCAD Part/PartDesign geometry creation.")


if __name__ == "__main__":
    main()
