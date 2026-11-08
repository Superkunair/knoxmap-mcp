"""Phase 1 tests, run against the real KnoxMap install (KNOXMAP_DIR).

Run with KnoxMap's interpreter:
    C:\\Users\\Jordan\\Desktop\\knoxmap\\.venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters, stdio_client, ClientSession

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from knoxmap_mcp import server  # noqa: E402
from knoxmap_mcp.bridge import KnoxBridge, KnoxMapError  # noqa: E402

PHASE1_TOOLS = {"knoxmap_status", "list_maps", "get_map_summary",
                "get_zone_settings_schema", "get_zones", "get_edits", "get_sketch"}


def call(name, args=None):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args or {})
    return anyio.run(go)


def payload(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


class Bridge(unittest.TestCase):
    def test_rejects_unsafe_map_names(self):
        for bad in ("../app", "a/b", "", "x y", "..\\x"):
            with self.subTest(bad=bad), self.assertRaises(KnoxMapError):
                KnoxBridge.check_map_name(bad)

    def test_missing_install_is_explained(self):
        b = KnoxBridge(ROOT / "does-not-exist")
        with self.assertRaises(KnoxMapError) as cm:
            b.get("/api/maps")
        self.assertIn("app.py", str(cm.exception))


class Tools(unittest.TestCase):
    def test_phase1_tools_are_listed(self):
        async def go():
            async with Client(server.mcp) as c:
                return await c.list_tools()
        names = {t.name for t in anyio.run(go).tools}
        self.assertTrue(PHASE1_TOOLS <= names, names)

    def test_status_reports_version_and_checks(self):
        out = payload(call("knoxmap_status"))
        self.assertTrue(out["version"])
        self.assertIn("ready", out)
        self.assertTrue(out["passing"] or out["failing"])

    def test_list_maps(self):
        out = payload(call("list_maps"))
        self.assertIsInstance(out["maps"], list)

    def test_zone_schema_has_limits(self):
        out = payload(call("get_zone_settings_schema"))
        ids = {s["id"] for s in out["settings"]}
        self.assertIn("max_levels", ids)
        self.assertTrue(all("min" in s and "max" in s for s in out["settings"]))

    def test_bad_name_is_a_tool_error(self):
        r = call("get_map_summary", {"map_name": "../secrets"})
        self.assertTrue(r.is_error)

    def test_unknown_map_is_a_tool_error(self):
        r = call("get_zones", {"map_name": "no_such_map_xyz"})
        self.assertTrue(r.is_error)


class Stdio(unittest.TestCase):
    """Over a real stdio pipe, a print() inside a tool must not break the protocol."""

    def test_print_in_a_tool_does_not_corrupt_stdout(self):
        script = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(ROOT / 'src')!r})
            from knoxmap_mcp import server
            @server.mcp.tool()
            async def noisy() -> str:
                print("KnoxMap-style build chatter on stdout")
                return "fine"
            server.main()
        """)
        params = StdioServerParameters(command=sys.executable, args=["-c", script],
                                       env={**os.environ})

        async def go():
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    a = await s.call_tool("noisy", {})
                    b = await s.call_tool("list_maps", {})
                    return a, b
        a, b = anyio.run(go)
        self.assertEqual(a.content[0].text, "fine")
        self.assertFalse(b.is_error)


if __name__ == "__main__":
    unittest.main()
