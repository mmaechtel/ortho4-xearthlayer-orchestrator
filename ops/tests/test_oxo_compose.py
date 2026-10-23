import importlib.machinery
import importlib.util
import tempfile
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
