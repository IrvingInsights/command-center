# PeakHinge FreeCAD

This repo section contains a parameter-driven FreeCAD workflow for evaluating the highest-risk mechanism interfaces of the PeakHinge deployable shelter system.

## Scope
This does **not** attempt to model the full building first.
It focuses on the interfaces that determine whether the concept is mechanically sane:
- pipe-through-bore pivot joint
- ridge scissor intersection and deployed lock
- floor cassette corner, hinge line, and bearing/compression interface

## Canonical units
- millimeters for all geometry
- degrees for angular parameters

## Modeling principles
- Model interfaces before full assemblies
- Expose all key dimensions in parameter files
- Prefer script-generated geometry over manual GUI-only modeling
- Export each subassembly to STEP, STL, and SVG when practical
- Keep each script focused on one subassembly

## First build order
1. Pipe pivot
2. Ridge scissor + lock
3. Cassette corner + bearing

## Output policy
Each script should create:
- FreeCAD model file
- STEP export
- STL export where useful
- SVG or 2D outline where useful
- screenshot or saved view if practical
