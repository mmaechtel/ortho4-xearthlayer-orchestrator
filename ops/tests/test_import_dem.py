import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "import-dem"
loader = importlib.machinery.SourceFileLoader("import_dem", str(SCRIPT))
spec = importlib.util.spec_from_loader("import_dem", loader)
import_dem = importlib.util.module_from_spec(spec)
loader.exec_module(import_dem)


class BlockOf(unittest.TestCase):
    def test_matches_ortho4xp_round_latlon(self):
        cases = {
            "N48E011.hgt": "+40+010",
            "N00E030.hgt": "+00+030",
            "N09W001.hgt": "+00-010",
            "S01W073.hgt": "-10-080",
            "S10E000.hgt": "-10+000",
            "N55W132.hgt": "+50-140",
        }
        for name, block in cases.items():
            self.assertEqual(import_dem.block_of(name), block, name)

    def test_non_hgt_names_are_ignored(self):
        for name in ("NED13_x.tif", "N48E011.tif", ".DS_Store", "N48E011.hgt.part"):
            self.assertIsNone(import_dem.block_of(name), name)


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src, self.dest = root / "src", root / "dest"
        self.src.mkdir()
        (self.src / "N48E011.hgt").write_bytes(b"a" * 10)
        (self.src / "S01W073.hgt").write_bytes(b"b" * 10)
        (self.src / "README.txt").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_places_each_hgt_in_its_block(self):
        import_dem.run(self.src, self.dest, dry_run=False, copy=import_dem.plain_copy)
        self.assertEqual((self.dest / "+40+010" / "N48E011.hgt").read_bytes(), b"a" * 10)
        self.assertTrue((self.dest / "-10-080" / "S01W073.hgt").is_file())
        self.assertFalse(any(self.dest.rglob("README.txt")))

    def test_rerun_skips_files_already_present(self):
        import_dem.run(self.src, self.dest, dry_run=False, copy=import_dem.plain_copy)
        copied = import_dem.run(self.src, self.dest, dry_run=False, copy=import_dem.plain_copy)
        self.assertEqual(copied, 0)

    def test_dry_run_writes_nothing(self):
        copied = import_dem.run(self.src, self.dest, dry_run=True, copy=import_dem.plain_copy)
        self.assertEqual(copied, 2)
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
