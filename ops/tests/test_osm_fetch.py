import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "osm-fetch"
loader = importlib.machinery.SourceFileLoader("osm_fetch", str(SCRIPT))
spec = importlib.util.spec_from_loader("osm_fetch", loader)
osm_fetch = importlib.util.module_from_spec(spec)
loader.exec_module(osm_fetch)

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


def box(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def feature(rid, polygons, pbf=True):
    base = f"https://download.geofabrik.de/europe/{rid.replace('/', '-')}"
    urls = {"updates": base + "-updates"}
    if pbf:
        urls["pbf"] = base + "-latest.osm.pbf"
    return {"type": "Feature", "properties": {"id": rid, "urls": urls},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons}}


# europe 0..20 x 40..60; germany 5..15 x 47..55 with a hole 9..11 x 50..52;
# luxembourg 5.5..7.5 x 48.5..51.5; two islands 0..3 and 10..13 at 40..43
INDEX = {"type": "FeatureCollection", "features": [
    feature("europe", [[box(0, 40, 20, 60)]]),
    feature("germany", [[box(5, 47, 15, 55), box(9, 50, 11, 52)[::-1]]]),
    feature("luxembourg", [[box(5.5, 48.5, 7.5, 51.5)]]),
    feature("two-islands", [[box(0, 40, 3, 43)], [box(10, 40, 13, 43)]]),
    feature("no-pbf", [[box(0, 40, 20, 60)]], pbf=False),
]}


def regions():
    return osm_fetch.regions(INDEX)


class Names(unittest.TestCase):
    def test_parse_tile(self):
        self.assertEqual(osm_fetch.parse_tile("+53-003"), (53, -3))
        self.assertEqual(osm_fetch.parse_tile("-01+179"), (-1, 179))
        with self.assertRaises(ValueError):
            osm_fetch.parse_tile("53-3")

    def test_file_stem_replaces_slashes(self):
        self.assertEqual(osm_fetch.file_stem("us/texas"), "us-texas")


class Geometry(unittest.TestCase):
    def test_regions_skip_entries_without_a_pbf(self):
        self.assertEqual({r.id for r in regions()}, {"europe", "germany", "luxembourg", "two-islands"})

    def test_area_subtracts_holes_and_adds_polygons(self):
        by = {r.id: r.area for r in regions()}
        self.assertEqual(by["germany"], 10 * 8 - 2 * 2)
        self.assertEqual(by["two-islands"], 18)

    def test_which_is_the_smallest_region_wholly_containing_the_tile(self):
        self.assertEqual(osm_fetch.which(regions(), 49, 6).id, "luxembourg")
        self.assertEqual(osm_fetch.which(regions(), 48, 7).id, "germany")
        self.assertEqual(osm_fetch.which(regions(), 45, 2).id, "europe")

    def test_a_border_tile_needs_the_larger_region(self):
        self.assertEqual(osm_fetch.which(regions(), 49, 5).id, "germany")  # lux starts at 5.5

    def test_a_hole_excludes_the_tile(self):
        self.assertEqual(osm_fetch.which(regions(), 50, 9).id, "europe")

    def test_tile_spanning_two_polygons_is_not_wholly_inside_either(self):
        self.assertEqual(osm_fetch.which(regions(), 41, 2).id, "two-islands")
        self.assertEqual(osm_fetch.which(regions(), 41, 3).id, "europe")

    def test_nothing_contains_a_tile_in_the_sea(self):
        self.assertIsNone(osm_fetch.which(regions(), 0, 0))

    def test_containing_lists_all_candidates_smallest_first(self):
        self.assertEqual([r.id for r in osm_fetch.containing(regions(), 49, 6)],
                         ["luxembourg", "germany", "europe"])


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "osm-extracts.tsv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_ledger_is_empty(self):
        self.assertEqual(osm_fetch.read_ledger(self.path), [])

    def test_append_and_read_round_trip(self):
        osm_fetch.append_ledger(self.path, "us/texas", "us-texas-261022.osm.pbf", "2026-10-22T20:21:33Z", "abc", "2026-10-23T10:00:00Z")
        [e] = osm_fetch.read_ledger(self.path)
        self.assertEqual((e.region, e.file, e.timestamp, e.md5, e.fetched),
                         ("us/texas", "us-texas-261022.osm.pbf", ts("2026-10-22T20:21:33Z"), "abc", "2026-10-23T10:00:00Z"))
        self.assertEqual(self.path.read_text().count("\n"), 1)

    def test_newest_per_region_is_the_latest_timestamp(self):
        for region, t in (("a", "2026-01-01T00:00:00Z"), ("a", "2026-03-01T00:00:00Z"), ("b", "2026-02-01T00:00:00Z"),
                          ("a", "2026-02-01T00:00:00Z")):
            osm_fetch.append_ledger(self.path, region, f"{region}.pbf", t, "m", "x")
        newest = osm_fetch.newest(osm_fetch.read_ledger(self.path))
        self.assertEqual(newest["a"].timestamp, ts("2026-03-01T00:00:00Z"))
        self.assertEqual(newest["b"].timestamp, ts("2026-02-01T00:00:00Z"))

    def test_the_seeded_ledger_names_the_two_extracts_on_disk(self):
        seeded = osm_fetch.newest(osm_fetch.read_ledger(osm_fetch.LEDGER))
        self.assertEqual(seeded["great-britain"].file, "great-britain-261022.osm.pbf")
        self.assertEqual(seeded["luxembourg"].md5, "22b22c6cd747f234895aaf78f7987156")
        self.assertEqual(seeded["luxembourg"].timestamp, ts("2026-10-22T20:21:33Z"))


class Freshness(unittest.TestCase):
    def test_ninety_days_is_still_fresh_one_second_more_is_not(self):
        edge = NOW - timedelta(days=90)
        self.assertTrue(osm_fetch.is_fresh(edge, NOW))
        self.assertFalse(osm_fetch.is_fresh(edge - timedelta(seconds=1), NOW))

    def test_max_age_is_a_constant_of_ninety_days(self):
        self.assertEqual(osm_fetch.MAX_AGE_DAYS, 90)

    def test_state_txt_timestamp_has_escaped_colons(self):
        text = "# original OSM minutely replication sequence number 7340294\ntimestamp=2026-10-22T20\\:21\\:33Z\nsequenceNumber=4941\n"
        self.assertEqual(osm_fetch.parse_state(text), ts("2026-10-22T20:21:33Z"))

    def test_state_without_timestamp_is_an_error(self):
        with self.assertRaises(osm_fetch.FetchError):
            osm_fetch.parse_state("sequenceNumber=1\n")
