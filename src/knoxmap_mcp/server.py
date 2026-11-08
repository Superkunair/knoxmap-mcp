"""knoxmap-mcp: an MCP server over a local KnoxMap install.

Phase 1: status and read-only map tools. Edit, zone and pipeline tools come
in later phases (see README.md).
"""
from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .bridge import KnoxBridge, KnoxMapError

INSTRUCTIONS = """\
Tools for KnoxMap, which turns real places (OpenStreetMap) into Project Zomboid
Build 42 maps. Maps live in KnoxMap's output folder and are named by folder.
Start with knoxmap_status and list_maps. get_zone_settings_schema gives the
settings a zone may override and their limits - stay inside them.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)

bridge = KnoxBridge()
mcp = MCPServer("knoxmap", instructions=INSTRUCTIONS, version="0.1.0")


async def _call(fn, *args, **kwargs) -> Any:
    """Run a bridge call off the event loop; turn KnoxMap refusals into tool errors."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except KnoxMapError as exc:
        raise ToolError(str(exc)) from exc


def _map_path(name: str) -> str:
    try:
        return KnoxBridge.check_map_name(name)
    except KnoxMapError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations=READ_ONLY)
async def knoxmap_status() -> dict[str, Any]:
    """Whether the KnoxMap install is ready: version, folder, and each setup
    check (PZ Mapping Tools, compiler, game tiles...) with how to fix a failing one."""
    report = await _call(bridge.get, "/api/setup-status")
    checks = report.get("checks", []) if isinstance(report, dict) else []
    failing = [c for c in checks if not c.get("ok")]
    maps = await _call(bridge.get, "/api/maps")
    return {
        "knoxmapDir": str(bridge.dir),
        "version": maps.get("current"),
        "ready": not failing,
        "failing": [{"id": c.get("id"), "label": c.get("label"),
                     "fix": c.get("fix")} for c in failing],
        "passing": [c.get("label") for c in checks if c.get("ok")],
    }


@mcp.tool(annotations=READ_ONLY)
async def list_maps() -> dict[str, Any]:
    """The maps in KnoxMap's output folder, with size, area and pipeline state."""
    return await _call(bridge.get, "/api/maps")


@mcp.tool(annotations=READ_ONLY)
async def get_map_summary(map_name: str) -> dict[str, Any]:
    """One map: bbox, metres per tile, rotation, cell count, the settings it
    was made with, which pipeline stages are done or needed, and install state."""
    return await _call(bridge.get, f"/api/maps/{_map_path(map_name)}")


@mcp.tool(annotations=READ_ONLY)
async def get_zone_settings_schema() -> dict[str, Any]:
    """The settings a zone may override (id, default, min, max, int), the wall
    styles a zone may pin, and the key used for the wall style."""
    return await _call(bridge.get, "/api/zones")


@mcp.tool(annotations=READ_ONLY)
async def get_zones(map_name: str) -> dict[str, Any]:
    """The zones drawn on a map: polygons with their own settings overrides."""
    return await _call(bridge.get, f"/api/zones/{_map_path(map_name)}")


@mcp.tool(annotations=READ_ONLY)
async def get_edits(map_name: str) -> dict[str, Any]:
    """The changes kept for a map's OSM features: removed ids, moved shapes,
    and tags added or overwritten, each keyed by OSM id."""
    return await _call(bridge.get, f"/api/edits/{_map_path(map_name)}")


@mcp.tool(annotations=READ_ONLY)
async def get_sketch(map_name: str) -> dict[str, Any]:
    """Features drawn by hand onto a map, as a GeoJSON FeatureCollection."""
    return await _call(bridge.get, f"/api/sketch/{_map_path(map_name)}")


def main() -> None:
    mcp.run("stdio")
