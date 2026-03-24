# Agent Guide

You are working on a parameter-driven FreeCAD project for a deployable hinge-based shelter system.

## Your role
You are not redesigning the whole building.
You are building, revising, and exporting mechanism subassemblies so the geometry, motion path, and attachment logic can be evaluated.

## Hard rules
1. Model interfaces before modeling architecture.
2. Use millimeters as the canonical unit.
3. Keep one subassembly per script.
4. Every important dimension must live in a parameter file.
5. Never hard-code dimensions that are likely to change.
6. Keep pivot clearances explicit.
7. Do not hide critical fastener logic inside insulated cavities.
8. Favor mechanically honest load paths over visually neat concepts.
9. When uncertain, preserve simplicity and expose the assumption in comments.
10. Do not claim structural validity. This repo is for geometry, kinematics, and pre-engineering development.

## Project priorities
Highest-risk areas, in order:
1. Ridge scissor + deployed lock geometry
2. Detachable weather-tight panel attachment/seam concept
3. Cassette corner + hinge line + compression/bearing interface
4. Repeating pipe-through-bore pivot detail

## Required outputs for each subassembly
- .FCStd model
- STEP export
- STL export if useful
- notes on assumptions
- simple text log of what changed

## Default assumptions unless overridden in params
- Structural wood members are rectangular solids for early-stage modeling
- Pipe pivots are ideal cylinders
- UHMW sleeves are modeled as separate sleeve bodies
- Clearances are modeled explicitly, not assumed to be zero
- Locking concepts should be generated as interchangeable variants where possible

## Naming conventions
- snake_case for scripts and parameters
- version suffixes only when a geometry branch meaningfully changes
- example: ridge_scissor_v1.json, build_ridge_scissor.py

## What success looks like
Success means:
- the geometry builds reliably
- the fold/deploy path is understandable
- clearances and collisions can be checked
- alternative lock concepts can be compared
- exported files are organized and repeatable

Failure means:
- modeling the whole shelter before the interfaces work
- burying important assumptions in code
- producing attractive but mechanically vague geometry
