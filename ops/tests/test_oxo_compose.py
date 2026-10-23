import importlib.machinery
import importlib.util
import http.server
import os
import tempfile
import threading
import contextlib
import io
import sys
import tomllib
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "oxo-compose"
loader = importlib.machinery.SourceFileLoader("oxo_compose", str(SCRIPT))
spec = importlib.util.spec_from_loader("oxo_compose", loader)
oxo_compose = importlib.util.module_from_spec(spec)
loader.exec_module(oxo_compose)

BASELINE = """
tiles = ["+51+000"]
[metadata]
name = "Example Region"
region_code = "EX"
revision = 1
[parameters]
provider = "GO2"
zoom = 16
include_overlays = true
[parameters.raw]
masking_mode = "3steps"
masks_width = "[10,20,30]"
road_level = "1"
[target]
root = "/srv/oxo/artifacts/EX"
[failure_policy]
max_attempts = 3
backoff_seconds = 60
"""

HOUSE = """
[parameters]
provider = "BI"
zoom = 17
include_overlays = false
[parameters.raw]
road_level = "3"
"""

PACKAGE = """
[metadata]
name = "eu_pilot"
region_code = "EU-PILOT"
revision = 2
[target]
root = "/mnt/xplane_data/oxo/artifacts/eu_pilot"

[[group]]
tiles = ["+48+010", "+48+011"]

[[group]]
id = "sand"
tiles = ["+48+012"]
zoom = 18
raw = { masking_mode = "sand", masks_width = "25" }
"""


def compose(package=PACKAGE, house=HOUSE, baseline=BASELINE):
    return oxo_compose.compose(tomllib.loads(baseline), tomllib.loads(house), tomllib.loads(package))


class Layers(unittest.TestCase):
    def test_one_spec_per_group(self):
        self.assertEqual(len(compose()), 2)

    def test_house_overrides_baseline_and_baseline_fills_the_rest(self):
        first = compose()[0]
        p = first["parameters"]
        self.assertEqual((p["provider"], p["zoom"], p["include_overlays"]), ("BI", 17, False))
        self.assertEqual(p["raw"]["road_level"], "3")
        self.assertEqual(p["raw"]["masking_mode"], "3steps")
        self.assertEqual(first["failure_policy"], {"max_attempts": 3, "backoff_seconds": 60})

    def test_group_overrides_house_for_its_tiles_only(self):
        first, second = compose()
        self.assertEqual(second["tiles"], ["+48+012"])
        self.assertEqual(second["parameters"]["zoom"], 18)
        self.assertEqual(second["parameters"]["raw"]["masking_mode"], "sand")
        self.assertEqual(second["parameters"]["raw"]["masks_width"], "25")
        self.assertEqual(second["parameters"]["raw"]["road_level"], "3")
        self.assertEqual(first["parameters"]["raw"]["masking_mode"], "3steps")

    def test_package_supplies_identity_and_target_not_the_baseline(self):
        first, second = compose()
        for s in (first, second):
            self.assertEqual(s["metadata"]["name"], "eu_pilot")
            self.assertEqual(s["metadata"]["revision"], 2)
            self.assertEqual(s["target"]["root"], "/mnt/xplane_data/oxo/artifacts/eu_pilot")
        self.assertEqual(first["tiles"], ["+48+010", "+48+011"])

    def test_region_code_per_group_is_stable_by_id_or_position(self):
        first, second = compose()
        self.assertEqual(first["metadata"]["region_code"], "EU-PILOT-1")
        self.assertEqual(second["metadata"]["region_code"], "EU-PILOT-SAND")

    def test_single_group_keeps_the_plain_region_code(self):
        one = PACKAGE.split("[[group]]\nid")[0]
        (only,) = compose(package=one)
        self.assertEqual(only["metadata"]["region_code"], "EU-PILOT")

    def test_package_level_parameters_apply_to_all_groups(self):
        pkg = PACKAGE.replace("[[group]]", "[parameters.raw]\nmin_area = \"0.01\"\n\n[[group]]", 1)
        for s in compose(package=pkg):
            self.assertEqual(s["parameters"]["raw"]["min_area"], "0.01")

    def test_a_tile_in_two_groups_is_refused(self):
        pkg = PACKAGE.replace('tiles = ["+48+012"]', 'tiles = ["+48+011"]')
        with self.assertRaises(oxo_compose.ComposeError):
            compose(package=pkg)

    def test_group_id_that_is_not_a_valid_region_code_part_is_refused(self):
        pkg = PACKAGE.replace('id = "sand"', 'id = "bad_group"')
        with self.assertRaisesRegex(oxo_compose.ComposeError, "EU-PILOT-BAD_GROUP"):
            compose(package=pkg)

    def test_duplicate_group_ids_are_refused(self):
        pkg = PACKAGE.replace('[[group]]\ntiles', '[[group]]\nid = "sand"\ntiles', 1)
        with self.assertRaisesRegex(oxo_compose.ComposeError, "EU-PILOT-SAND"):
            compose(package=pkg)

    def test_group_id_colliding_with_a_positional_index_is_refused(self):
        pkg = PACKAGE.replace('id = "sand"', 'id = "1"')
        with self.assertRaisesRegex(oxo_compose.ComposeError, "EU-PILOT-1"):
            compose(package=pkg)

    def test_overlong_region_code_is_refused(self):
        pkg = PACKAGE.replace('id = "sand"', 'id = "' + "A" * 512 + '"')
        with self.assertRaises(oxo_compose.ComposeError):
            compose(package=pkg)

    def test_bad_base_region_code_is_refused(self):
        one = PACKAGE.split("[[group]]\nid")[0].replace("EU-PILOT", "eu_pilot")
        with self.assertRaises(oxo_compose.ComposeError):
            compose(package=one)

    def test_region_code_with_trailing_newline_is_refused(self):
        one = PACKAGE.split("[[group]]\nid")[0].replace('"EU-PILOT"', '"EU-PILOT\\n"')
        with self.assertRaises(oxo_compose.ComposeError):
            compose(package=one)

    def test_no_groups_is_refused(self):
        with self.assertRaises(oxo_compose.ComposeError):
            compose(package=PACKAGE.split("[[group]]")[0])


class Output(unittest.TestCase):
    def test_emitted_toml_round_trips(self):
        for s in compose():
            self.assertEqual(tomllib.loads(oxo_compose.to_toml(s)), s)

    def test_write_names_files_by_region_code(self):
        with tempfile.TemporaryDirectory() as d:
            paths = oxo_compose.write(compose(), Path(d))
            self.assertEqual(sorted(p.name for p in paths), ["EU-PILOT-1.toml", "EU-PILOT-SAND.toml"])


if __name__ == "__main__":
    unittest.main()


class Origins(unittest.TestCase):
    def test_only_values_differing_from_baseline_are_attributed_to_their_layer(self):
        first, second = oxo_compose.origins(
            tomllib.loads(BASELINE), tomllib.loads(HOUSE), tomllib.loads(PACKAGE))
        self.assertEqual(first, {"provider": "house", "zoom": "house",
                                 "include_overlays": "house", "road_level": "house"})
        self.assertEqual(second["zoom"], "group sand")
        self.assertEqual(second["masking_mode"], "group sand")
        self.assertEqual(second["masks_width"], "group sand")

    def test_a_value_reset_to_the_baseline_is_not_a_deviation(self):
        pkg = PACKAGE.replace("zoom = 18", "zoom = 16")
        _, second = oxo_compose.origins(tomllib.loads(BASELINE), tomllib.loads(HOUSE), tomllib.loads(pkg))
        self.assertNotIn("zoom", second)

    def test_package_level_parameters_are_attributed_to_the_package(self):
        pkg = PACKAGE.replace("[[group]]", "[parameters.raw]\nmin_area = \"0.01\"\n\n[[group]]", 1)
        first, _ = oxo_compose.origins(tomllib.loads(BASELINE), tomllib.loads(HOUSE), tomllib.loads(pkg))
        self.assertEqual(first["min_area"], "package")


class SubmitRefusal(unittest.TestCase):
    def submit_with(self, package):
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.send_response(500)
                self.end_headers()

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "pkg.toml"
            pkg.write_text(package)
            argv = sys.argv
            sys.argv = ["oxo-compose", str(pkg), "--submit", f"http://127.0.0.1:{server.server_port}"]
            try:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
                    oxo_compose.main()
            finally:
                sys.argv = argv
                server.shutdown()
        return hits, str(cm.exception)

    def test_bad_group_id_makes_no_request(self):
        hits, msg = self.submit_with(PACKAGE.replace('id = "sand"', 'id = "bad_group"'))
        self.assertEqual(hits, [])
        self.assertIn("BAD_GROUP", msg)

    def test_duplicate_region_codes_make_no_request(self):
        hits, msg = self.submit_with(PACKAGE.replace('id = "sand"', 'id = "1"'))
        self.assertEqual(hits, [])
        self.assertIn("duplicate region_code EU-PILOT-1", msg)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.dem, self.patches, self.ledger = root / "dem", root / "patches", root / "ledger"
        (self.dem / "+40+010").mkdir(parents=True)
        with open(self.dem / "+40+010" / "N48E010.hgt", "wb") as f:
            f.truncate(25_934_402)
        with open(self.dem / "+40+010" / "N48E011.hgt", "wb") as f:
            f.truncate(2_884_802)
        (self.patches / "+40+010" / "+48+011").mkdir(parents=True)
        (self.patches / "+40+010" / "+48+011" / "EDDM.patch.osm").write_text("x")
        self.env = oxo_compose.Env(
            now="2026-10-24T10:00:00Z", ops_commit="0ccb5b2", ortho4xp_commit="c363134", image_id="sha256:abc123",
            patches_tree="3a9e", dem_dir=self.dem, patches_dir=self.patches, ledger_dir=self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, created=True):
        spec = compose()[0]
        return spec, oxo_compose.record(spec, {"provider": "house"}, "job-1", created, self.env)

    def test_record_holds_spec_and_provenance(self):
        spec, path = self.record()
        self.assertEqual(path, self.ledger / "eu_pilot" / "EU-PILOT-1-r2.toml")
        rec = tomllib.loads(path.read_text())
        self.assertEqual(rec["spec"], spec)
        p = rec["provenance"]
        self.assertEqual((p["job_id"], p["submitted"], p["ops_commit"], p["ortho4xp_commit"], p["image_id"], p["patches_tree"]),
                         ("job-1", "2026-10-24T10:00:00Z", "0ccb5b2", "c363134", "sha256:abc123", "3a9e"))
        self.assertEqual(p["overrides"], {"provider": "house"})

    def test_record_classifies_dem_and_lists_patches_per_tile(self):
        _, path = self.record()
        tiles = tomllib.loads(path.read_text())["tiles"]
        self.assertEqual(tiles["+48+010"], {"dem": "1s", "patches": []})
        self.assertEqual(tiles["+48+011"], {"dem": "3s", "patches": ["EDDM.patch.osm"]})

    def test_missing_dem_is_recorded_as_missing(self):
        spec = compose()[1]
        path = oxo_compose.record(spec, {}, "job-2", True, self.env)
        self.assertEqual(tomllib.loads(path.read_text())["tiles"]["+48+012"]["dem"], "missing")

    def test_an_existing_job_does_not_overwrite_its_record(self):
        _, path = self.record()
        path.write_text("# original\n")
        self.record(created=False)
        self.assertEqual(path.read_text(), "# original\n")

    def test_a_renamed_package_does_not_get_a_second_record_for_an_existing_job(self):
        _, first = self.record()
        spec = compose()[0]
        spec["metadata"]["name"] = "renamed"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            path = oxo_compose.record(spec, {}, "job-1", False, self.env)
        self.assertEqual(path, first)
        self.assertFalse((self.ledger / "renamed").exists())
        self.assertIn(str(first), buf.getvalue())

    def test_keys_that_are_not_bare_are_quoted(self):
        self.assertEqual(tomllib.loads(oxo_compose.to_toml({"t": {"+48+011": {"dem": "1s"}}})),
                         {"t": {"+48+011": {"dem": "1s"}}})
