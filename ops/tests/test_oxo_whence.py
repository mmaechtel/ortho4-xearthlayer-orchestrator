import contextlib
import importlib.machinery
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "oxo-whence"
loader = importlib.machinery.SourceFileLoader("oxo_whence", str(SCRIPT))
spec = importlib.util.spec_from_loader("oxo_whence", loader)
oxo_whence = importlib.util.module_from_spec(spec)
loader.exec_module(oxo_whence)


def entry(submitted, job, code, rev, tiles, overrides='provider = "house"', masking="3steps"):
    tile_tables = "".join(f'\n[tiles."{t}"]\ndem = "1s"\npatches = ["EDDM.patch.osm"]\n' for t in tiles)
    return f"""[provenance]
submitted = "{submitted}"
job_id = "{job}"
ops_commit = "0ccb5b2"
ortho4xp_commit = "c363134"
image_id = "sha256:abc123"
patches_tree = "3a9e"

[provenance.overrides]
{overrides}
{tile_tables}
[spec]
tiles = {list(tiles)!r}

[spec.metadata]
name = "oxo_pilot"
region_code = "{code}"
revision = {rev}

[spec.parameters]
provider = "BI"
zoom = 16

[spec.parameters.raw]
masking_mode = "{masking}"
""".replace("'", '"')


class Whence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name)
        d = self.ledger / "oxo_pilot"
        d.mkdir()
        (d / "EU-PILOT-r1.toml").write_text(entry("2026-10-24T10:00:00Z", "job-1", "EU-PILOT", 1, ["+48+010", "+48+011"]))
        (d / "EU-PILOT-r2.toml").write_text(entry("2026-10-26T10:00:00Z", "job-2", "EU-PILOT", 2, ["+48+011"],
                                                  'provider = "house"\nmasking_mode = "group sand"', "sand"))
        (d / "installs.log").write_text(
            "2026-10-25T08:00:00Z\tA4_PILOT\tzzXEL_oxo_pilot_ortho\t+48+010,+48+011\n"
            "2026-10-27T08:00:00Z\tA5_EU\tzzXEL_oxo_pilot_ortho\t+48+011\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, tile):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = oxo_whence.main([tile, "--ledger-dir", str(self.ledger)])
        return rc, out.getvalue()

    def test_builds_newest_first_with_provenance(self):
        rc, out = self.run_main("+48+011")
        self.assertEqual(rc, 0)
        self.assertLess(out.index("job-2"), out.index("job-1"))
        for s in ("EU-PILOT r2", "ops 0ccb5b2", "ortho4xp c363134", "image sha256:abc123", "patches 3a9e", "dem 1s", "EDDM.patch.osm"):
            self.assertIn(s, out)

    def test_deviations_show_value_and_layer(self):
        _, out = self.run_main("+48+011")
        self.assertIn("masking_mode=sand (group sand)", out)
        self.assertIn("provider=BI (house)", out)

    def test_installs_are_attributed_to_the_build_they_followed(self):
        _, out = self.run_main("+48+011")
        newest, older = out.split("job-1")[0], out.split("job-1")[1]
        self.assertIn("A5_EU", newest)
        self.assertNotIn("A4_PILOT", newest)
        self.assertIn("A4_PILOT", older)

    def test_installs_are_worded_as_after_the_submission(self):
        _, out = self.run_main("+48+011")
        self.assertIn("installed after this submission", out)
        (self.ledger / "oxo_pilot" / "installs.log").unlink()
        _, out = self.run_main("+48+010")
        self.assertIn("no install after this submission", out)

    def test_tile_only_in_older_build(self):
        rc, out = self.run_main("+48+010")
        self.assertEqual(rc, 0)
        self.assertIn("job-1", out)
        self.assertNotIn("job-2", out)

    def test_unknown_tile(self):
        rc, out = self.run_main("+01+001")
        self.assertEqual(rc, 1)
        self.assertIn("no ledger record", out)


if __name__ == "__main__":
    unittest.main()
