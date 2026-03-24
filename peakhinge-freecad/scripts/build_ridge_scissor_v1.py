"""
PeakHinge ridge scissor generator v1.

Creates a simplified geometry/interference study with:
- two rectangular rafter solids
- one ridge pipe axis
- sleeve geometry at the pivot zone
- three lock concept bodies:
  1. lock beam
  2. removable pin concept
  3. clamp plate concept

This is a kinematic/packaging study only.
It is not a structural validation model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

try:
    import FreeCAD as App  # type: ignore
    import Part  # type: ignore
    import Mesh  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("This script must be run inside FreeCAD or freecadcmd.") from exc


ROOT = Path(__file__).resolve().parents[1]
PARAM_PATH = ROOT / "params" / "ridge_scissor_v1.json"
MODELS_DIR = ROOT / "models"
EXPORT_STEP_DIR = ROOT / "exports" / "step"
EXPORT_STL_DIR = ROOT / "exports" / "stl"


OBJECT_NAMES = {
    "rafter_left": "rafter_left",
    "rafter_right": "rafter_right",
    "ridge_pipe": "ridge_pipe",
    "sleeve_left": "sleeve_left",
    "sleeve_right": "sleeve_right",
    "lock_beam": "lock_beam",
    "lock_pin": "lock_pin",
    "clamp_plate_left": "clamp_plate_left",
    "clamp_plate_right": "clamp_plate_right",
}


def load_params(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs() -> None:
    for d in (MODELS_DIR, EXPORT_STEP_DIR, EXPORT_STL_DIR):
        d.mkdir(parents=True, exist_ok=True)


def add_feature(doc, name: str, shape):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    return obj


def make_x_cylinder(length: float, radius: float, x: float, y: float, z: float):
    return Part.makeCylinder(radius, length, App.Vector(x, y, z), App.Vector(1, 0, 0))


def transform_shape(shape, translation=(0.0, 0.0, 0.0), rotation_axis=(1.0, 0.0, 0.0), angle_deg=0.0):
    placement = App.Placement()
    placement.Base = App.Vector(*translation)
    placement.Rotation = App.Rotation(App.Vector(*rotation_axis), angle_deg)
    new_shape = shape.copy()
    new_shape.Placement = placement.multiply(new_shape.Placement)
    return new_shape


def build_ridge_scissor(params: Dict[str, Any]):
    ensure_dirs()

    doc_name = params.get("name", "ridge_scissor_v1")
    doc = App.newDocument(doc_name)

    rafter_length = float(params["rafter_length"])
    rafter_width = float(params["rafter_width"])
    rafter_thickness = float(params["rafter_thickness"])
    ridge_pipe_od = float(params["ridge_pipe_outer_diameter"])
    sleeve_od = float(params["sleeve_outer_diameter"])
    sleeve_id = float(params["sleeve_inner_diameter"])
    deployment_angle = float(params["deployment_angle_degrees"])
    lock_clearance = float(params["lock_clearance"])
    lock_beam_width = float(params["lock_beam_width"])
    lock_beam_thickness = float(params["lock_beam_thickness"])
    pin_diameter = float(params["pin_diameter"])
    collision_buffer = float(params["collision_buffer"])

    ridge_pipe_radius = ridge_pipe_od / 2.0
    sleeve_outer_radius = sleeve_od / 2.0
    sleeve_inner_radius = sleeve_id / 2.0
    pin_radius = pin_diameter / 2.0

    # Simplified global coordinate logic:
    # - ridge axis runs along X
    # - Y is thickness direction
    # - Z is vertical
    # - pivot zone is centered around the origin in Y/Z, offset in X by small margin
    pivot_x = 0.0
    pivot_y = 0.0
    pivot_z = 0.0

    # Create base rafter as a rectangular prism with pivot at one end.
    # We center thickness around Y=0 to make symmetry easier.
    base_rafter = Part.makeBox(
        rafter_length,
        rafter_thickness,
        rafter_width,
        App.Vector(0, -rafter_thickness / 2.0, -rafter_width / 2.0),
    )

    # Position rafters so they meet at the ridge and open symmetrically.
    left_rafter = base_rafter.copy()
    right_rafter = base_rafter.copy()

    # Rotate around X axis to open around the ridge line.
    left_rafter = transform_shape(left_rafter, rotation_axis=(1.0, 0.0, 0.0), angle_deg=deployment_angle / 2.0)
    right_rafter = transform_shape(right_rafter, rotation_axis=(1.0, 0.0, 0.0), angle_deg=-(deployment_angle / 2.0))

    # Ridge pipe is a simple reference axis passing through the pivot zone.
    ridge_pipe_length = max(rafter_thickness * 4.0, 300.0)
    ridge_pipe = make_x_cylinder(
        ridge_pipe_length,
        ridge_pipe_radius,
        -ridge_pipe_length / 2.0,
        pivot_y,
        pivot_z,
    )

    # Sleeve bodies centered on the same axis, one for each rafter side as explicit interface geometry.
    sleeve_length = rafter_thickness
    sleeve_left_outer = make_x_cylinder(sleeve_length, sleeve_outer_radius, -sleeve_length - collision_buffer, pivot_y, pivot_z)
    sleeve_left_inner = make_x_cylinder(sleeve_length, sleeve_inner_radius, -sleeve_length - collision_buffer, pivot_y, pivot_z)
    sleeve_left = sleeve_left_outer.cut(sleeve_left_inner)

    sleeve_right_outer = make_x_cylinder(sleeve_length, sleeve_outer_radius, collision_buffer, pivot_y, pivot_z)
    sleeve_right_inner = make_x_cylinder(sleeve_length, sleeve_inner_radius, collision_buffer, pivot_y, pivot_z)
    sleeve_right = sleeve_right_outer.cut(sleeve_right_inner)

    # Lock concept 1: lock beam below ridge, spanning across both rafter faces.
    lock_beam_length = 220.0
    lock_beam = Part.makeBox(
        lock_beam_length,
        lock_beam_thickness,
        lock_beam_width,
        App.Vector(-lock_beam_length / 2.0, (rafter_thickness / 2.0) + lock_clearance, -(lock_beam_width / 2.0)),
    )

    # Lock concept 2: removable pin crossing the assembly perpendicular to the ridge pipe.
    lock_pin_length = (rafter_width * 1.5)
    lock_pin = Part.makeCylinder(
        pin_radius,
        lock_pin_length,
        App.Vector(pivot_x, -lock_pin_length / 2.0, 0.0),
        App.Vector(0, 1, 0),
    )

    # Lock concept 3: clamp plates as two external plates above and below the assembly.
    clamp_plate_length = 160.0
    clamp_plate_thickness = 8.0
    clamp_plate_width = 90.0

    clamp_plate_left = Part.makeBox(
        clamp_plate_length,
        clamp_plate_thickness,
        clamp_plate_width,
        App.Vector(-clamp_plate_length / 2.0, -(rafter_thickness / 2.0) - lock_clearance - clamp_plate_thickness, -(clamp_plate_width / 2.0)),
    )
    clamp_plate_right = Part.makeBox(
        clamp_plate_length,
        clamp_plate_thickness,
        clamp_plate_width,
        App.Vector(-clamp_plate_length / 2.0, (rafter_thickness / 2.0) + lock_clearance, -(clamp_plate_width / 2.0)),
    )

    objects = [
        add_feature(doc, OBJECT_NAMES["rafter_left"], left_rafter),
        add_feature(doc, OBJECT_NAMES["rafter_right"], right_rafter),
        add_feature(doc, OBJECT_NAMES["ridge_pipe"], ridge_pipe),
        add_feature(doc, OBJECT_NAMES["sleeve_left"], sleeve_left),
        add_feature(doc, OBJECT_NAMES["sleeve_right"], sleeve_right),
        add_feature(doc, OBJECT_NAMES["lock_beam"], lock_beam),
        add_feature(doc, OBJECT_NAMES["lock_pin"], lock_pin),
        add_feature(doc, OBJECT_NAMES["clamp_plate_left"], clamp_plate_left),
        add_feature(doc, OBJECT_NAMES["clamp_plate_right"], clamp_plate_right),
    ]

    doc.recompute()

    fcstd_path = MODELS_DIR / f"{doc_name}.FCStd"
    step_path = EXPORT_STEP_DIR / f"{doc_name}.step"
    stl_path = EXPORT_STL_DIR / f"{doc_name}.stl"

    doc.saveAs(str(fcstd_path))
    Part.export(objects, str(step_path))

    compound = Part.makeCompound([obj.Shape for obj in objects])
    helper = add_feature(doc, "mesh_export_compound_ridge", compound)
    Mesh.export([helper], str(stl_path))
    doc.removeObject(helper.Name)
    doc.recompute()
    doc.save()

    print(f"Saved FreeCAD model: {fcstd_path}")
    print(f"Saved STEP export:   {step_path}")
    print(f"Saved STL export:    {stl_path}")

    return doc


def main() -> None:
    params = load_params(PARAM_PATH)
    build_ridge_scissor(params)


if __name__ == "__main__":
    main()
