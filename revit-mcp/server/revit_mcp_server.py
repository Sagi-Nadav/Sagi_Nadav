"""MCP server that lets Claude control Autodesk Revit.

It forwards each tool call to the Revit add-in (RevitMcp.dll), which listens on
http://127.0.0.1:8765 inside Revit. Lengths are in meters.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

REVIT_URL = os.environ.get("REVIT_MCP_URL", "http://127.0.0.1:8765")
TIMEOUT = float(os.environ.get("REVIT_MCP_TIMEOUT", "130"))

mcp = FastMCP("revit")

Point = list[float]


def _call(command: str, **args: Any) -> Any:
    args = {k: v for k, v in args.items() if v is not None}
    try:
        r = httpx.post(f"{REVIT_URL}/command", json={"command": command, "args": args}, timeout=TIMEOUT)
    except httpx.ConnectError:
        raise RuntimeError(
            "Cannot reach Revit. Make sure Revit is open and the 'Revit MCP Bridge' add-in is loaded."
        ) from None
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Unknown Revit error"))
    return data.get("result")


# ---------------------------------------------------------------- read

@mcp.tool()
def get_model_info() -> Any:
    """Summary of the open Revit model: title, path, version, levels and element counts."""
    return _call("get_model_info")


@mcp.tool()
def list_levels() -> Any:
    """List levels with id, name and elevation (m)."""
    return _call("list_levels")


@mcp.tool()
def list_views() -> Any:
    """List printable views (plans, sections, 3D, sheets...)."""
    return _call("list_views")


@mcp.tool()
def set_active_view(name: str | None = None, id: int | None = None) -> Any:
    """Open a view in Revit by name or id."""
    return _call("set_active_view", name=name, id=id)


@mcp.tool()
def list_elements(category: str, level: str | None = None, limit: int = 200) -> Any:
    """List elements of a category.

    category: walls, floors, columns, beams, foundations, rebar, doors, windows, rooms,
    grids, roofs, stairs, generic models, or any BuiltInCategory such as OST_Walls.
    level: optional level name to filter by.
    """
    return _call("list_elements", category=category, level=level, limit=limit)


@mcp.tool()
def list_types(category: str) -> Any:
    """List available types (family: type) for a category, e.g. wall types or column sizes."""
    return _call("list_types", category=category)


@mcp.tool()
def get_element(id: int, include_type_parameters: bool = False) -> Any:
    """Get an element's location and all its parameters (values as shown in Revit)."""
    return _call("get_element", id=id, include_type_parameters=include_type_parameters)


@mcp.tool()
def get_selection() -> Any:
    """Elements currently selected by the user in Revit."""
    return _call("get_selection")


@mcp.tool()
def select_elements(ids: list[int], zoom: bool = True) -> Any:
    """Select elements in Revit (and zoom to them)."""
    return _call("select_elements", ids=ids, zoom=zoom)


@mcp.tool()
def get_quantities(category: str, level: str | None = None) -> Any:
    """Quantity takeoff for a category, grouped by type: count, volume (m3), area (m2), length (m).

    Useful for concrete volumes of walls, floors, columns, beams and foundations.
    """
    return _call("get_quantities", category=category, level=level)


# ---------------------------------------------------------------- modify

@mcp.tool()
def set_parameter(id: int, parameter: str, value: str, on_type: bool = False) -> Any:
    """Set a parameter value on an element (or on its type when on_type=True).

    Numeric values are given in the project's display units, e.g. "250" for 250 mm
    if the project uses millimeters, or with units like "3 m". Yes/No: "true"/"false".
    Note: changing a type parameter affects every element of that type.
    """
    return _call("set_parameter", id=id, parameter=parameter, value=value, on_type=on_type)


@mcp.tool()
def create_level(elevation_m: float, name: str | None = None) -> Any:
    """Create a new level at the given elevation (m)."""
    return _call("create_level", elevation_m=elevation_m, name=name)


@mcp.tool()
def create_wall(
    start: Point,
    end: Point,
    level: str | None = None,
    height_m: float = 3.0,
    wall_type: str | None = None,
    structural: bool = False,
    base_offset_m: float = 0.0,
) -> Any:
    """Create a straight wall from start [x, y] to end [x, y] (m) on a level.

    wall_type: type name or "Family: Type" (see list_types("walls")); default type if omitted.
    """
    return _call("create_wall", start=start, end=end, level=level, height_m=height_m,
                 wall_type=wall_type, structural=structural, base_offset_m=base_offset_m)


@mcp.tool()
def create_floor(
    points: list[Point],
    level: str | None = None,
    floor_type: str | None = None,
    structural: bool = True,
    offset_m: float | None = None,
) -> Any:
    """Create a floor/slab from a closed polygon of [x, y] points (m) on a level."""
    return _call("create_floor", points=points, level=level, floor_type=floor_type,
                 structural=structural, offset_m=offset_m)


@mcp.tool()
def place_column(
    points: list[Point],
    base_level: str | None = None,
    top_level: str | None = None,
    column_type: str | None = None,
    structural: bool = True,
) -> Any:
    """Place one or more columns at [x, y] points (m), from base_level to top_level.

    column_type: e.g. "40x40" or "Family: Type" (see list_types("columns")).
    The family must already be loaded in the project.
    """
    return _call("place_column", points=points, base_level=base_level, top_level=top_level,
                 column_type=column_type, structural=structural)


@mcp.tool()
def create_beam(start: Point, end: Point, level: str | None = None, beam_type: str | None = None) -> Any:
    """Create a structural beam from start to end [x, y] (m) on a level."""
    return _call("create_beam", start=start, end=end, level=level, beam_type=beam_type)


@mcp.tool()
def move_elements(ids: list[int], vector: Point) -> Any:
    """Move elements by a vector [dx, dy] or [dx, dy, dz] in meters."""
    return _call("move_elements", ids=ids, vector=vector)


@mcp.tool()
def delete_elements(ids: list[int]) -> Any:
    """Delete elements (and their dependents). Can be undone in Revit with Ctrl+Z."""
    return _call("delete_elements", ids=ids)


if __name__ == "__main__":
    mcp.run()
