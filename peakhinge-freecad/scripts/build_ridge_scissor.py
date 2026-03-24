"""
PeakHinge ridge scissor assembly generator.
Generates two simplified rafters, ridge axis, and placeholder lock variants.
"""

import json
from pathlib import Path

PARAM_PATH = Path("params/ridge_scissor_v1.json")


def load_params(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    p = load_params(PARAM_PATH)
    print("Loaded ridge scissor parameters:")
    for k, v in p.items():
        print(f"{k}: {v}")

    # FreeCAD geometry generation goes here.
    # Suggested first pass:
    # 1. Create two simplified rafter bodies
    # 2. Add pivot axis / pipe representation
    # 3. Position to deployment angle
    # 4. Add lock-beam variant body
    # 5. Add removable-pin variant reference
    # 6. Add clamp-plate variant reference
    # 7. Save and export

    print("TODO: implement FreeCAD geometry and variant generation.")


if __name__ == "__main__":
    main()
