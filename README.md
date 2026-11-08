# knoxmap-mcp

An MCP server for [KnoxMap](https://github.com/spytheeuclidean-a11y/knoxmap), the
tool that turns real places from OpenStreetMap into Project Zomboid Build 42 maps.
The goal is to let Claude read the details of specific zones of a map and make
the map more accurate, both in its OSM data (tags, footprints, heights) and in
game (density, wall styles, zombie spawns).

## How it works

The server runs on **KnoxMap's own Python** (`KnoxMap\.venv`), imports KnoxMap's
Flask `app`, and calls its routes through `app.test_client()`. Nothing has to be
open: no window, no port. The same route code runs as in the app, with the same
checks on tags, zone limits and map names.

Two things matter for the stdio transport:
- mcp 2.x sends fd 1 to stderr while the server runs, so anything KnoxMap prints
  can't corrupt the protocol (covered by a test).
- `app.py` reconfigures `sys.stdout` when imported, which fails once fd 1 is
  diverted, so the bridge points stdout at stderr during that import.

## Setup

```powershell
C:\Users\Jordan\Desktop\knoxmap\.venv\Scripts\python.exe -m pip install "mcp>=2.3,<3"
```

`.mcp.json` in this repo registers the server with Claude Code. Note that
re-running KnoxMap's Setup may rebuild its `.venv`; if it does, install `mcp`
again.

## Tools

| Phase | Tool | What it does |
|---|---|---|
| 1 ✅ | `knoxmap_status` | Version, install folder, setup checks and how to fix any that fail |
| 1 ✅ | `list_maps`, `get_map_summary` | Maps in `output/`: bbox, scale, settings, pipeline state |
| 1 ✅ | `get_zone_settings_schema` | Settings a zone may override, with limits and wall styles |
| 1 ✅ | `get_zones`, `get_edits`, `get_sketch` | What has been drawn or changed on a map |
| 2 | `query_zone`, `describe_zone`, `get_feature` | Features in a polygon and accuracy stats for it |
| 3 | `retag_feature`, `remove_feature`, `reshape_feature`, `upsert_zone`, `delete_zone`, `add_sketch_features`, `bulk_fix` | Changes, with dry runs and backups |
| 4 | `generate_map`, `rebuild_buildings`, `compile_map`, `install_map`, `job_progress`, `stop_job` | The pipeline, run as background jobs |
| 5 | Overture / Microsoft Buildings comparison | Flag footprints OSM is missing |

## Tests

```powershell
C:\Users\Jordan\Desktop\knoxmap\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
