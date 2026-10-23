import contextlib
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "oxo-package"
_loader = importlib.machinery.SourceFileLoader("oxo_package", str(SCRIPT))
_spec = importlib.util.spec_from_loader("oxo_package", _loader)
oxo_package = importlib.util.module_from_spec(_spec)
_loader.exec_module(oxo_package)


def make_tile(root, tile="+48+010", *, cfg=None, dsf_size=20000,
              ter="BASE_TEXTURE ../textures/24432_34768_BI17.dds\n", png=True,
              extra=None, block=None):
    d = root / f"zOrtho4XP_{tile}"
    (d / "terrain").mkdir(parents=True)
    (d / "textures").mkdir()
    if cfg is not None:
        (d / f"Ortho4XP_{tile}.cfg").write_text(f"zl=17\n{cfg}\nwater=1\n")
    if dsf_size is not None:
        nav = d / "Earth nav data" / (block or oxo_package.block_of(tile))
        nav.mkdir(parents=True)
        (nav / f"{tile}.dsf").write_bytes(b"x" * dsf_size)
    if ter is not None:
        (d / "terrain" / f"{tile}_BI17.ter").write_text(ter)
    if png:
        (d / "textures" / f"{tile}_mask.png").write_bytes(b"png")
    (d / "textures" / "ignored.dds").write_bytes(b"dds")
    for rel, data in (extra or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "artifacts"
        self.root.mkdir()
        self.pkgs = self.tmp / "packages"
        self.lock = self.tmp / "xearthlayer.lock"
        self.ledger = self.tmp / "ledger"
        self.spec = self.tmp / "spec.toml"
        self.write_spec("oxo_pilot")

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)], check=True)

    def write_spec(self, name):
        self.spec.write_text(
            'tiles = ["+48+010"]\n[metadata]\n'
            f'name = "{name}"\nregion_code = "EU"\nrevision = 1\n'
            '[parameters]\nprovider = "BI"\nzoom = 17\ninclude_overlays = false\n'
            f'[target]\nroot = "{self.root}"\n')

    def run_main(self, *args, code="A4_PILOT"):
        out, err = io.StringIO(), io.StringIO()
        argv = [str(self.spec), "--code", code, "--packages-dir", str(self.pkgs),
                "--lock-file", str(self.lock), "--ledger-dir", str(self.ledger), *args]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = oxo_package.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()

    @property
    def pkg(self):
        return self.pkgs / "zzXEL_oxo_pilot_ortho"


class Packaging(Base):
    def test_valid_tiles_packaged_into_layout(self):
        make_tile(self.root, "+48+010")
        make_tile(self.root, "-33-071", extra={"textures/-33-071_extra.png": b"p"})
        rc, out, err = self.run_main()
        self.assertEqual(rc, 0, err)
        self.assertTrue((self.pkg / "Earth nav data/+40+010/+48+010.dsf").is_file())
        self.assertTrue((self.pkg / "Earth nav data/-40-080/-33-071.dsf").is_file())
        self.assertTrue((self.pkg / "terrain/+48+010_BI17.ter").is_file())
        self.assertTrue((self.pkg / "terrain/-33-071_BI17.ter").is_file())
        self.assertEqual(sorted(p.name for p in (self.pkg / "textures").iterdir()),
                         ["+48+010_mask.png", "-33-071_extra.png", "-33-071_mask.png"])
        self.assertFalse(any((self.pkg / "Earth nav data").glob("*/*.cfg")))

    def test_metadata_file_format(self):
        make_tile(self.root)
        rc, _, err = self.run_main()
        self.assertEqual(rc, 0, err)
        lines = (self.pkg / "xearthlayer_scenery_package.txt").read_text().split("\n")
        self.assertEqual(lines[:3], ["REGIONAL SCENERY PACKAGE", "1.0.0", "A4_PILOT  99.99.99"])
        self.assertRegex(lines[3], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(lines[4:], ["Z", "zzXEL_oxo_pilot_ortho",
                                     "zzXEL_oxo_pilot_ortho-99.99.99.tar.gz", "0", ""])

    def test_rerun_is_idempotent(self):
        make_tile(self.root)
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.run_main()[0], 0)
        self.assertTrue((self.pkg / "Earth nav data/+40+010/+48+010.dsf").is_file())

    def test_rebuild_leaves_no_stale_files(self):
        # a ZL16 rebuild must not leave the ZL17 terrain and masks of the build before
        d = make_tile(self.root)
        (d / "textures" / "old_ZL17.png").write_bytes(b"png")
        self.assertEqual(self.run_main()[0], 0)
        (d / "terrain" / "+48+010_BI17.ter").rename(d / "terrain" / "+48+010_BI16.ter")
        (d / "textures" / "old_ZL17.png").unlink()
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual([p.name for p in (self.pkg / "terrain").iterdir()], ["+48+010_BI16.ter"])
        self.assertEqual([p.name for p in (self.pkg / "textures").iterdir()], ["+48+010_mask.png"])
        self.assertEqual(sorted(p.name for p in self.pkgs.iterdir()), ["zzXEL_oxo_pilot_ortho"])

    def test_no_tiles_fails(self):
        rc, _, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertIn("no zOrtho4XP_", err)

    def test_block_of_uses_floor(self):
        self.assertEqual(oxo_package.block_of("+48+010"), "+40+010")
        self.assertEqual(oxo_package.block_of("-05-001"), "-10-010")
        self.assertEqual(oxo_package.block_of("+00+000"), "+00+000")


class CodeValidation(Base):
    def test_valid_codes_accepted(self):
        for code in ("A4_PILOT", "eu-1", "X"):
            with self.subTest(code=code):
                self.tearDown(); self.setUp()
                make_tile(self.root)
                rc, _, err = self.run_main(code=code)
                self.assertEqual(rc, 0, err)

    def test_invalid_codes_rejected_before_anything_is_written(self):
        make_tile(self.root)
        self.lock.write_text(f"{os.getpid()}\n")  # a live lock must not mask the code error
        for code in ("", "a/b", "..", "a b", "a..b/", "_x", "A5_EU\n"):
            with self.subTest(code=code):
                rc, out, err = self.run_main(code=code)
                self.assertNotEqual(rc, 0)
                self.assertIn("invalid --code", err)
                self.assertFalse(self.pkgs.exists())
                self.assertFalse(self.ledger.exists())


class StrictRules(Base):
    def assert_rejected(self, reason, *args, **tile_kw):
        make_tile(self.root, "+48+010")
        make_tile(self.root, "+48+011", **tile_kw)
        rc, out, err = self.run_main(*args)
        self.assertNotEqual(rc, 0)
        self.assertIn(f"+48+011: {reason}", out + err)
        self.assertFalse(self.pkg.exists(), "nothing may be copied on rejection")

    def test_tile_without_cfg_is_valid(self):
        # the worker withholds Ortho4XP_<tile>.cfg from egress
        make_tile(self.root)
        rc, _, err = self.run_main()
        self.assertEqual(rc, 0, err)

    def test_no_dsf(self):
        self.assert_rejected("no DSF", dsf_size=None)

    def test_dsf_too_small(self):
        self.assert_rejected("DSF too small: 10000B", dsf_size=10000)

    def test_no_ter(self):
        self.assert_rejected("no .ter files", ter=None)

    def test_ter_not_bi(self):
        self.assert_rejected("no BI provider in .ter",
                             ter="BASE_TEXTURE ../textures/1_2_GO217.dds\n")

    def test_no_png(self):
        self.assert_rejected("no .png masks", png=False)

    def test_partial_files(self):
        for name in ("textures/a.tmp", "x.part", "Earth nav data/+40+010/y.partial"):
            with self.subTest(name=name):
                self.tearDown(); self.setUp()
                self.assert_rejected("partial files present", extra={name: b""})

    def test_stale_dsf_bak(self):
        make_tile(self.root, "+48+010")
        d = make_tile(self.root, "+48+011")
        dsf = d / "Earth nav data/+40+010/+48+011.dsf"
        bak = Path(str(dsf) + ".bak")
        bak.write_bytes(b"old")
        os.utime(dsf, (1000, 1000))
        rc, out, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertIn("+48+011: stale DSF (.bak newer)", out + err)

    def test_bad_tile_dir_name(self):
        make_tile(self.root, "+48+010")
        (self.root / "zOrtho4XP_junk").mkdir()
        rc, out, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertIn("junk: bad tile name", out + err)

    def test_lists_at_most_ten(self):
        for i in range(12):
            make_tile(self.root, f"+48+0{i:02d}", ter=None)
        rc, out, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertEqual((out + err).count("no .ter files"), 10)
        self.assertIn("(2 more)", out + err)


class LooseMode(Base):
    def test_loose_accepts_missing_png(self):
        make_tile(self.root, png=False)
        rc, _, err = self.run_main("--loose")
        self.assertEqual(rc, 0, err)
        self.assertTrue((self.pkg / "Earth nav data/+40+010/+48+010.dsf").is_file())

    def test_loose_keeps_bi_rules(self):
        make_tile(self.root, png=False, ter="BASE_TEXTURE ../textures/1_2_GO217.dds\n")
        rc, out, err = self.run_main("--loose")
        self.assertNotEqual(rc, 0)
        self.assertIn("no BI provider in .ter", out + err)


class DryRun(Base):
    def test_dry_run_changes_nothing(self):
        make_tile(self.root)
        rc, out, err = self.run_main("--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertFalse(self.pkgs.exists())
        self.assertIn("dry-run", out)

    def test_dry_run_reports_rejections(self):
        make_tile(self.root, ter=None)
        rc, out, err = self.run_main("--dry-run")
        self.assertNotEqual(rc, 0)
        self.assertIn("no .ter files", out + err)
        self.assertFalse(self.pkgs.exists())


class Lock(Base):
    def test_live_lock_refuses(self):
        make_tile(self.root)
        self.lock.write_text(f"{os.getpid()}\n")
        rc, _, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertIn("xearthlayer run", err)
        self.assertFalse(self.pkgs.exists())

    def test_stale_lock_warns_and_proceeds(self):
        make_tile(self.root)
        p = subprocess.Popen(["true"]); p.wait()
        self.lock.write_text(f"{p.pid}\n")
        rc, _, err = self.run_main()
        self.assertEqual(rc, 0, err)
        self.assertIn("stale", err)
        self.assertTrue(self.lock.exists())
        self.assertTrue(self.pkg.is_dir())

    def test_empty_lock_is_fine(self):
        make_tile(self.root)
        self.lock.write_text("")
        self.assertEqual(self.run_main()[0], 0)

    def test_default_lock_path_honours_xdg(self):
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = "/x/state"
        try:
            self.assertEqual(oxo_package.default_lock_file(),
                             Path("/x/state/xearthlayer/xearthlayer.lock"))
        finally:
            if old is None:
                del os.environ["XDG_STATE_HOME"]
            else:
                os.environ["XDG_STATE_HOME"] = old


class Spec(Base):
    def test_unsafe_name_rejected(self):
        make_tile(self.root)
        for name in ("../evil", "a/b", "", ".hidden", "a b"):
            with self.subTest(name=name):
                self.write_spec(name)
                rc, _, err = self.run_main()
                self.assertNotEqual(rc, 0)
                self.assertIn("unsafe", err)
        self.assertFalse(self.pkgs.exists())

    def test_missing_target_root_fails(self):
        self.root.rmdir()
        rc, _, err = self.run_main()
        self.assertNotEqual(rc, 0)
        self.assertIn("not found", err)



class InstallsLog(Base):
    def test_each_install_appends_one_line(self):
        make_tile(self.root, "+48+010")
        make_tile(self.root, "+48+011")
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.run_main()[0], 0)
        lines = (self.ledger / "oxo_pilot" / "installs.log").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        when, code, pkg, tiles = lines[0].split("\t")
        self.assertRegex(when, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual((code, pkg, tiles), ("A4_PILOT", "zzXEL_oxo_pilot_ortho", "+48+010,+48+011"))

    def test_dry_run_and_rejection_log_nothing(self):
        make_tile(self.root, "+48+010")
        self.run_main("--dry-run")
        make_tile(self.root, "+48+011", png=False)
        self.run_main()
        self.assertFalse((self.ledger / "oxo_pilot" / "installs.log").exists())


if __name__ == "__main__":
    unittest.main()
