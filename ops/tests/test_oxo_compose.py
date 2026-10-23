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
from datetime import datetime, timezone
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


ADOPTED_APT = """[package]
name = "eu_apt"
dir = "/x"
code = "A0_EU"
version = "99.99.99"
adopted = "2026-10-23T12:00:00Z"

[tiles."+48+011"]
observed = {creation_agent = "osxp", textures = {BI17 = 20, BI18 = 5}, mask_zl = [17], dsf_bytes = 1}
cfg_status = "agrees"
cfg_source = "/o/zOrtho4XP_+48+011/Ortho4XP_+48+011.cfg"
[tiles."+48+011".cfg]
default_website = "BI"
default_zl = "17"
masking_mode = "rocks"
road_level = "3"
custom_dem = "x"
"""

ADOPTED_SONNY = """[package]
name = "eu_sonny"
dir = "/y"
code = "A5_EU"
version = "99.99.99"
adopted = "2026-10-23T12:00:00Z"

[tiles."+48+011"]
observed = {creation_agent = "Ortho4XP", textures = {BI16 = 9}, mask_zl = [16], dsf_bytes = 1}
cfg_status = "none"

[tiles."+48+010"]
observed = {creation_agent = "Ortho4XP", textures = {BI16 = 3, BI18 = 1}, mask_zl = [16], dsf_bytes = 1}
cfg_status = "rejected"
"""

ONE_GROUP = """
[metadata]
name = "oxo_apt"
region_code = "OXO-APT"
revision = 1
[target]
root = "/a"

[[group]]
id = "eddm"
tiles = ["+48+011"]
"""


class Legacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.adopted = Path(self.tmp.name)
        (self.adopted / "eu_apt.toml").write_text(ADOPTED_APT)
        (self.adopted / "eu_sonny.toml").write_text(ADOPTED_SONNY)

    def tearDown(self):
        self.tmp.cleanup()

    def legacy(self, package=ONE_GROUP):
        pkg = tomllib.loads(package)
        specs = compose(package)
        return [oxo_compose.legacy(spec, g, self.adopted)
                for spec, g in zip(specs, pkg["group"])]

    def test_the_copy_in_use_is_the_highest_priority_adoption(self):
        known = oxo_compose.known_legacy(self.adopted, "+48+011")
        self.assertEqual(known["package"], "eu_apt")
        self.assertEqual(known["status"], "agrees")

    def test_known_values_map_cfg_keys_onto_spec_parameters(self):
        known = oxo_compose.known_legacy(self.adopted, "+48+011")["values"]
        self.assertEqual(known["zoom"], 17)
        self.assertEqual(known["provider"], "BI")
        self.assertEqual(known["masking_mode"], "rocks")

    def test_without_cfg_only_the_observed_provider_and_base_zl_are_known(self):
        known = oxo_compose.known_legacy(self.adopted, "+48+010")
        self.assertEqual(known["values"], {"provider": "BI", "zoom": 16})

    def test_differing_values_are_undecided_until_the_group_decides(self):
        (diff,) = self.legacy()
        undecided = diff["undecided"]
        self.assertEqual(set(undecided), {"masking_mode"})  # provider, zoom 17 and road_level 3 agree with house
        self.assertEqual(undecided["masking_mode"], {"legacy": {"rocks": ["+48+011"]}, "composed": "3steps"})
        self.assertNotIn("custom_dem", undecided)  # not a spec parameter

    def test_keep_needs_the_override_and_then_the_difference_is_gone(self):
        pkg = ONE_GROUP + 'raw = { masking_mode = "rocks" }\n[group.legacy]\nmasking_mode = "keep: rocks look right"\n' \
              'zoom = "default: ZL16 everywhere"\nroad_level = "default: samsoir"\n'
        (diff,) = self.legacy(pkg)
        self.assertEqual(diff["undecided"], {})
        self.assertEqual(diff["decisions"]["masking_mode"], "keep: rocks look right")

    def test_keep_without_the_override_is_refused(self):
        pkg = ONE_GROUP + '[group.legacy]\nmasking_mode = "keep: rocks"\n'
        with self.assertRaises(oxo_compose.ComposeError):
            self.legacy(pkg)

    def test_a_decision_must_say_keep_or_default(self):
        pkg = ONE_GROUP + '[group.legacy]\nmasking_mode = "maybe"\n'
        with self.assertRaises(oxo_compose.ComposeError):
            self.legacy(pkg)

    def test_the_legacy_table_is_not_a_parameter(self):
        pkg = ONE_GROUP + '[group.legacy]\nzoom = "default: x"\n'
        self.assertNotIn("legacy", compose(pkg)[0]["parameters"])
        self.assertEqual(oxo_compose.origins(tomllib.loads(BASELINE), tomllib.loads(HOUSE), tomllib.loads(pkg)),
                         [{"provider": "house", "zoom": "house", "include_overlays": "house", "road_level": "house"}])

    def test_tiles_record_which_legacy_copy_they_replace(self):
        (diff,) = self.legacy()
        self.assertEqual(diff["tiles"], {"+48+011": "eu_apt (A0_EU) cfg agrees"})


class GroupSelection(unittest.TestCase):
    def test_select_keeps_only_the_named_group(self):
        pkg = tomllib.loads(PACKAGE)
        specs = compose()
        picked = oxo_compose.select(specs, pkg["group"], "sand")
        self.assertEqual([s["metadata"]["region_code"] for s, _ in picked], ["EU-PILOT-SAND"])

    def test_unknown_group_is_refused(self):
        with self.assertRaises(oxo_compose.ComposeError):
            oxo_compose.select(compose(), tomllib.loads(PACKAGE)["group"], "nope")


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


BAKED = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc).timestamp()  # OsmGate.fill's baked-at


class OsmGate(unittest.TestCase):
    """The pre-build OSM check (#16): refuses --submit before any request unless --force."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache"
        self.cache.mkdir()
        self.saved = (oxo_compose.OSM_CACHE, oxo_compose.osm_fetch.load_index)
        oxo_compose.OSM_CACHE = self.cache
        oxo_compose.osm_fetch.load_index = lambda d, now: {"features": []}  # never the network
        self.hits = []
        hits = self.hits

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.send_response(500)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        oxo_compose.OSM_CACHE, oxo_compose.osm_fetch.load_index = self.saved
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_main(self, *flags, package=PACKAGE.replace('+48+', '+10+')):
        pkg = Path(self.tmp.name) / "pkg.toml"
        pkg.write_text(package)
        argv = sys.argv
        sys.argv = ["oxo-compose", str(pkg), *flags]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                try:
                    oxo_compose.main()
                    msg = ""
                except SystemExit as e:
                    msg = str(e)
        finally:
            sys.argv = argv
        return out.getvalue(), msg

    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def fill(self, tile, extract="2026-10-22T20:21:33Z"):
        lat, lon = int(tile[:3]), int(tile[3:])
        for layer in oxo_compose.osm_fetch.osm_bake.LAYERS:
            p = oxo_compose.osm_fetch.osm_bake.layer_path(self.cache, lat, lon, layer)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
            os.utime(p, (BAKED - 60, BAKED - 60))  # written before the bake was logged
        with open(self.cache / "osm-bake.log", "a") as f:
            f.write(f"{tile}\t{extract}\tx.osm.pbf\t2026-10-23T10:00:00Z\n")

    def test_submit_is_refused_without_osm_data_and_makes_no_request(self):
        _, msg = self.run_main("--submit", self.url())
        self.assertEqual(self.hits, [])
        for tile in ("+10+010", "+10+011", "+10+012"):
            self.assertIn(f"{tile}: layers missing", msg)
        self.assertIn("--force", msg)

    def test_only_the_selected_group_counts(self):
        self.fill("+10+012")
        _, msg = self.run_main("--submit", self.url(), "--group", "sand")
        self.assertNotIn("OSM", msg)  # gate passed; whatever stops it later is not OSM
        self.assertNotIn("layers missing", msg)

    def test_force_skips_the_check(self):
        _, msg = self.run_main("--submit", self.url(), "--force")
        self.assertNotIn("layers missing", msg)

    def test_a_malformed_tile_name_is_a_clean_refusal(self):
        _, msg = self.run_main("--osm-check", package=PACKAGE.replace('"+48+012"', '"48+12"'))
        self.assertIn("oxo-compose:", msg)
        self.assertIn("48+12", msg)

    def test_osm_check_reports_without_submitting(self):
        _, msg = self.run_main("--osm-check")
        self.assertIn("+10+010: layers missing", msg)
        self.assertEqual(self.hits, [])

    def test_osm_check_with_submit_is_refused_and_posts_nothing(self):
        for t in ("+10+010", "+10+011", "+10+012"):
            self.fill(t, "2099-01-01T00:00:00Z")
        _, msg = self.run_main("--osm-check", "--submit", self.url(), "--force")
        self.assertIn("--osm-check", msg)
        self.assertEqual(self.hits, [])

    def test_osm_check_passes_quietly_when_everything_is_ready(self):
        for t in ("+10+010", "+10+011", "+10+012"):
            self.fill(t)
        # a fixed 'now' is not injectable here, so use an extract that cannot age out
        text = (self.cache / "osm-bake.log").read_text().replace("2026-10-22T20:21:33Z", "2099-01-01T00:00:00Z")
        (self.cache / "osm-bake.log").write_text(text)
        out, msg = self.run_main("--osm-check")
        self.assertEqual(msg, "")
        self.assertIn("3 tiles", out)


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

    def test_an_existing_job_without_a_record_gets_none_written(self):
        # its provenance is unknown: current commits would describe a different build
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            path = oxo_compose.record(compose()[0], {}, "job-1", False, self.env)
        self.assertIsNone(path)
        self.assertEqual(list(self.ledger.rglob("*.toml")), [])
        self.assertIn("no ledger record", buf.getvalue())

    def test_keys_that_are_not_bare_are_quoted(self):
        self.assertEqual(tomllib.loads(oxo_compose.to_toml({"t": {"+48+011": {"dem": "1s"}}})),
                         {"t": {"+48+011": {"dem": "1s"}}})
