"""The Puente Grande prison test map (Tonalá / El Salto, Jalisco, MX).

Two prisons sit side by side in OSM: the state Penal de Puente Grande and the
federal CEFERESO No. 2. Each gets a zone of rural houses (KnoxMap's rural preset:
two storeys at most, no flats, big footprints cut into house-sized units,
few zombies, heavy trees). The expected zones live in
puente_grande_zones.json; the map itself is made in KnoxMap's output folder.

Skipped when the map has not been generated on this machine.
"""
import json
import sys
import unittest
from pathlib import Path

import anyio
from mcp import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from knoxmap_mcp import server  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "puente_grande_zones.json")
                     .read_text(encoding="utf-8"))
MAP = FIXTURE["map"]


def call(name, args=None):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args or {})
    r = anyio.run(go)
    if r.is_error:
        raise AssertionError(r.content[0].text)
    if r.structured_content is not None:
        return r.structured_content
    return json.loads(r.content[0].text)


def _have_map() -> bool:
    try:
        names = {m.get("mapName") for m in call("list_maps")["maps"]}
    except Exception:  # noqa: BLE001 - no install means nothing to test
        return False
    return MAP in names


@unittest.skipUnless(_have_map(), f"map {MAP!r} not generated in KnoxMap")
class PuenteGrandeZones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = call("get_zone_settings_schema")
        cls.zones = {z["name"]: z for z in call("get_zones", {"map_name": MAP})["zones"]}

    def test_both_prisons_are_zoned(self):
        self.assertEqual(set(self.zones), {z["name"] for z in FIXTURE["zones"]})

    def test_zones_match_fixture(self):
        for want in FIXTURE["zones"]:
            with self.subTest(zone=want["name"]):
                got = self.zones[want["name"]]
                self.assertEqual(got.get("wall_style"), want["wall_style"])
                for key, value in want["settings"].items():
                    self.assertAlmostEqual(got["settings"][key], value, places=6)
                self.assertEqual(len(got["ring"]), len(want["ring"]))

    def test_settings_inside_schema_limits(self):
        limits = {s["id"]: s for s in self.schema["settings"]}
        for want in FIXTURE["zones"]:
            self.assertIn(want["wall_style"], self.schema["styles"])
            for key, value in want["settings"].items():
                with self.subTest(zone=want["name"], key=key):
                    self.assertIn(key, limits)
                    self.assertGreaterEqual(value, limits[key]["min"])
                    self.assertLessEqual(value, limits[key]["max"])

    def test_zones_inside_map_bbox(self):
        b = FIXTURE["bbox"]
        for zone in self.zones.values():
            for lon, lat in zone["ring"]:
                self.assertTrue(b["west"] <= lon <= b["east"], (zone["name"], lon))
                self.assertTrue(b["south"] <= lat <= b["north"], (zone["name"], lat))

    def test_map_summary_has_the_area(self):
        out = call("get_map_summary", {"map_name": MAP})
        self.assertTrue(out)

    def test_buildings_follow_their_zone(self):
        """Every building placed inside a prison zone has the zone's wall
        style and no more floors than its max_levels."""
        import csv
        import os
        summary = call("get_map_summary", {"map_name": MAP})
        if not summary.get("buildingsReady"):
            self.skipTest("buildings not generated yet")
        knox = Path(os.environ.get("KNOXMAP_DIR", r"C:\Users\Jordan\Desktop\knoxmap"))
        sys.path.insert(0, str(knox))
        from generator.rendering.projection import Projector
        from shapely.geometry import Point, Polygon

        b = summary["bbox"]
        proj = Projector.build(b["south"], b["west"], b["north"], b["east"],
                               summary["metersPerTile"], summary["rotation"])
        placements = knox / "output" / MAP / f"{MAP}_placements.csv"
        with placements.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for want in FIXTURE["zones"]:
            poly = Polygon([proj.to_px(lat, lon) for lon, lat in want["ring"]])
            inside = [r for r in rows if poly.contains(Point(
                int(r["tile_x"]) + int(r["width"]) / 2,
                int(r["tile_y"]) + int(r["height"]) / 2))]
            with self.subTest(zone=want["name"]):
                self.assertGreater(len(inside), 0)
                for r in inside:
                    self.assertEqual(r["style"].split("~")[-1], want["wall_style"], r["file"])
                    self.assertLessEqual(int(r["levels"]), want["settings"]["max_levels"], r["file"])
                    if want["settings"].get("apartment_chance") == 0:
                        self.assertNotEqual(r["kind"], "apartment", r["file"])


if __name__ == "__main__":
    unittest.main()
