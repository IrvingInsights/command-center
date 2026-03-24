"""
PeakHinge pipe-through-bore pivot generator v1.

This script is designed to be readable first and clever second.
It creates a simple pipe-pivot study from JSON parameters.

Intended use:
- run inside a FreeCAD Python environment or freecadcmd
- generate a rib block, bore, sleeve, pivot pipe, and washer/end-stop
- save an FCStd model and export STEP/STL where supported

Notes:
- This is early-stage geometry only.
- It is not structural validation.
- Export behavior may vary slightly across FreeCAD installs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    import FreeCAD as App  # type: ignore
    import Part  # type: ignore
    import Mesh  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "This script must be run inside FreeCAD or freecadcmd."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
PARAM_PATH = ROOT / "params" / "pipe_pivot_v1.json"
MODELS_DIR = ROOT / "models"
EXPORT_STEP_DIR = ROOT / "exports" / "step"
EXPORT_STL_DIR = ROOT / "exports" / "stl"


OBJECT_NAMES = {
    "rib": "rib_block",
    "sleeve": "pivot_sleeve",
    "pipe": "pivot_pipe",
    "washer": "retention_washer",
}


def load_params(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs() -> None:
    for d in (MODELS_DIR, EXPORT_STEP_DIR, EXPORT_STL_DIR):
        d.mkdir(parents=True, exist_ok=True)


def make_cylinder(length: float, radius: float, center_y: float, center_z: float):
    """Create a cylinder whose axis runs along X."""
    base = App.Vector(0, center_y, center_z)
    direction = App.Vector(1, 0, 0)
    return Part.makeCylinder(radius, length, base, direction)


def add_feature(doc, name: str, shape):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    return obj


def build_pipe_pivot(params: Dict[str, Any]):
    ensure_dirs()

    doc_name = params.get("name", "pipe_pivot_v1")
    doc = App.newDocument(doc_name)

    rib_length = float(params["rib_length"])
    rib_height = float(params["rib_height"])
    rib_thickness = float(params["rib_thickness"])
    pipe_od = float(params["pipe_outer_diameter"])
    bore_diameter = float(params["bore_diameter"])
    sleeve_od = float(params["sleeve_outer_diameter"])
    sleeve_id = float(params["sleeve_inner_diameter"])
    sleeve_length = float(params["sleeve_length"])
    edge_distance = float(params["edge_distance"])
    washer_od = float(params["washer_outer_diameter"])
    washer_id = float(params["washer_inner_diameter"])
    retention_gap = float(params["retention_gap"])

    pipe_radius = pipe_od / 2.0
    bore_radius = bore_diameter / 2.0
    sleeve_outer_radius = sleeve_od / 2.0
    sleeve_inner_radius = sleeve_id / 2.0
    washer_outer_radius = washer_od / 2.0
    washer_inner_radius = washer_id / 2.0

    center_y = rib_thickness / 2.0
    center_z = edge_distance + bore_radius

    if center_z + bore_radius > rib_height:
        raise ValueError(
            "Bore center and diameter exceed rib height. Adjust edge_distance or bore_diameter."
        )

    if sleeve_length > rib_thickness:
        raise ValueError("Sleeve length cannot exceed rib thickness in this simplified model.")

    rib_block = Part.makeBox(rib_length, rib_thickness, rib_height)
    bore_cylinder = make_cylinder(rib_length, bore_radius, center_y, center_z)
    rib_with_bore = rib_block.cut(bore_cylinder)

    sleeve_start_x = (rib_length - sleeve_length) / 2.0
    sleeve_outer = Part.makeCylinder(
        sleeve_outer_radius,
        sleeve_length,
        App.Vector(sleeve_start_x, center_y, center_z),
        App.Vector(1, 0, 0),
    )
    sleeve_inner = Part.makeCylinder(
        sleeve_inner_radius,
        sleeve_length,
        App.Vector(sleeve_start_x, center_y, center_z),
        App.Vector(1, 0, 0),
    )
    sleeve_shape = sleeve_outer.cut(sleeve_inner)

    pipe_length = rib_length + (2.0 * retention_gap) + washer_od * 0.5
    pipe_start_x = -retention_gap - (washer_od * 0.25)
    pipe_shape = Part.makeCylinder(
        pipe_radius,
        pipe_length,
        App.Vector(pipe_start_x, center_y, center_z),
        App.Vector(1, 0, 0),
    )

    washer_thickness = max(3.0, rib_thickness * 0.08)
    washer_x = pipe_start_x + pipe_length - washer_thickness
    washer_outer = Part.makeCylinder(
        washer_outer_radius,
        washer_thickness,
        App.Vector(washer_x, center_y, center_z),
        App.Vector(1, 0, 0),
    )
    washer_inner = Part.makeCylinder(
        washer_inner_radius,
        washer_thickness,
        App.Vector(washer_x, center_y, center_z),
        App.Vector(1, 0, 0),
    )
    washer_shape = washer_outer.cut(washer_inner)

    rib_obj = add_feature(doc, OBJECT_NAMES["rib"], rib_with_bore)
    sleeve_obj = add_feature(doc, OBJECT_NAMES["sleeve"], sleeve_shape)
    pipe_obj = add_feature(doc, OBJECT_NAMES["pipe"], pipe_shape)
    washer_obj = add_feature(doc, OBJECT_NAMES["washer"], washer_shape)

    doc.recompute()

    fcstd_path = MODELS_DIR / f"{doc_name}.FCStd"
    step_path = EXPORT_STEP_DIR / f"{doc_name}.step"
    stl_path = EXPORT_STL_DIR / f"{doc_name}.stl"

    doc.saveAs(str(fcstd_path))

    Part.export([rib_obj, sleeve_obj, pipe_obj, washer_obj], str(step_path))

    compound = Part.makeCompound([
        rib_obj.Shape,
        sleeve_obj.Shape,
        pipe_obj.Shape,
        washer_obj.Shape,
    ])
    Mesh.export([add_feature(doc, "mesh_export_compound", compound)], str(stl_path))

    # Clean up the helper object so the document stays simple.
    helper = doc.getObject("mesh_export_compound")
    if helper is not None:
        doc.removeObject(helper.Name)
        doc.recompute()
        doc.save()

    print(f"Saved FreeCAD model: {fcstd_path}")
    print(f"Saved STEP export:   {step_path}")
    print(f"Saved STL export:    {stl_path}")

    return doc


def main() -> None:
    params = load_params(PARAM_PATH)
    build_pipe_pivot(params)


if __name__ == "__main__":
    main()
