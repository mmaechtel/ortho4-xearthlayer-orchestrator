import bz2
import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "osm-bake"
loader = importlib.machinery.SourceFileLoader("osm_bake", str(SCRIPT))
spec = importlib.util.spec_from_loader("osm_bake", loader)
osm_bake = importlib.util.module_from_spec(spec)
loader.exec_module(osm_bake)

LAYERS = ["airports", "big_roads", "small_roads", "coastline", "water"]


class FakeOsmium:
    """Stands in for subprocess.run: records argv, creates the -o file."""

    def __init__(self, skip_output_of=()):
        self.calls = []
        self.skip = skip_output_of

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[:2] == ["osmium", "fileinfo"]:
            return type("R", (), {"stdout": "2026-10-22T20:21:02Z\n"})()
        out = Path(argv[argv.index("-o") + 1])
        if not any(s in out.name for s in self.skip):
            out.write_bytes(b"data:" + out.name.encode())
        return type("R", (), {"stdout": ""})()


class Names(unittest.TestCase):
    def test_tile_and_block_names_match_ortho4xp(self):
        self.assertEqual(osm_bake.tile_name(48, 11), "+48+011")
        self.assertEqual(osm_bake.tile_name(53, -3), "+53-003")
        self.assertEqual(osm_bake.tile_name(-1, -73), "-01-073")
        self.assertEqual(osm_bake.block_name(48, 11), "+40+010")
        self.assertEqual(osm_bake.block_name(53, -3), "+50-010")
        self.assertEqual(osm_bake.block_name(-1, -73), "-10-080")

    def test_layer_path_is_the_cache_layout(self):
        p = osm_bake.layer_path(Path("/c"), 48, 11, "big_roads")
        self.assertEqual(str(p), "/c/+40+010/+48+011/+48+011_big_roads.osm.bz2")

    def test_layers_are_the_five_the_cache_holds(self):
        self.assertEqual(list(osm_bake.LAYERS), LAYERS)


class Commands(unittest.TestCase):
    def test_prefilter_unions_all_selectors(self):
        argv = osm_bake.prefilter_cmd(Path("in.pbf"), Path("pre.pbf"))
        self.assertEqual(argv[:3], ["osmium", "tags-filter", "in.pbf"])
        for sel in ("nwr/aeroway", "w/natural=coastline", "w/highway=motorway,trunk,primary,secondary",
                    "w/highway=tertiary,unclassified,residential,service,track"):
            self.assertIn(sel, argv)
        self.assertIn("--overwrite", argv)
        self.assertEqual(argv[argv.index("-o") + 1], "pre.pbf")

    def test_extract_cmd_uses_smart_and_one_degree_bbox(self):
        # smart also completes multipolygon relations (water, airports); with
        # complete_ways Ortho4XP drops relations whose members lie outside
        argv = osm_bake.extract_cmd(Path("pre.pbf"), Path("t.pbf"), 48, 11)
        self.assertEqual(argv[:2], ["osmium", "extract"])
        self.assertEqual(argv[argv.index("-s") + 1], "smart")
        self.assertEqual(argv[argv.index("-b") + 1], "11,48,12,49")
        self.assertEqual(argv[argv.index("-o") + 1], "t.pbf")
        self.assertIn("pre.pbf", argv)

    def test_extract_cmd_negative_coordinates(self):
        argv = osm_bake.extract_cmd(Path("p"), Path("t"), -1, -73)
        self.assertEqual(argv[argv.index("-b") + 1], "-73,-1,-72,0")

    def test_filter_cmd_writes_bz2_xml(self):
        argv = osm_bake.filter_cmd(Path("t.pbf"), Path("o.part"), "coastline")
        self.assertEqual(argv[:3], ["osmium", "tags-filter", "t.pbf"])
        self.assertIn("w/natural=coastline", argv)
        self.assertEqual(argv[argv.index("-f") + 1], "osm.bz2")
        self.assertEqual(argv[argv.index("-o") + 1], "o.part")
        self.assertIn("--overwrite", argv)

    def test_water_selectors_cover_rels_and_ways(self):
        self.assertEqual(set(osm_bake.LAYERS["water"]),
                         {"r/natural=water", "r/waterway=riverbank", "w/natural=water",
                          "w/waterway=riverbank,dock"})

    def test_small_roads_is_the_widest_road_level(self):
        self.assertEqual(osm_bake.LAYERS["small_roads"],
                         ["w/highway=tertiary,unclassified,residential,service,track"])


class BakeTile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "cache"
        self.work = Path(self.tmp.name) / "work"
        self.work.mkdir()
        self.dir = self.out / "+40+010" / "+48+011"

    def fill(self, layers, content=b"old"):
        self.dir.mkdir(parents=True, exist_ok=True)
        for l in layers:
            (self.dir / f"+48+011_{l}.osm.bz2").write_bytes(content)

    def bake(self, run, force=False):
        return osm_bake.bake_tile(self.out, 48, 11, Path("pre.pbf"), self.work, force, run)

    def test_bakes_all_layers_atomically(self):
        run = FakeOsmium()
        self.assertEqual(self.bake(run), 5)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         sorted(f"+48+011_{l}.osm.bz2" for l in LAYERS))
        self.assertEqual(sum(c[1] == "extract" for c in run.calls), 1)
        self.assertEqual(sum(c[1] == "tags-filter" for c in run.calls), 5)
        for c in run.calls:
            if c[1] == "tags-filter":
                self.assertTrue(c[c.index("-o") + 1].endswith(".part"))
        self.assertEqual(list(self.out.rglob("*.part")), [])

    def test_empty_layer_becomes_empty_osm_file(self):
        self.bake(FakeOsmium(skip_output_of=("coastline",)))
        text = bz2.open(self.dir / "+48+011_coastline.osm.bz2", "rt").read()
        self.assertIn("<osm ", text)
        self.assertIn("</osm>", text)
        self.assertNotIn("<node", text)

    def test_existing_layers_are_skipped(self):
        self.fill(LAYERS)
        run = FakeOsmium()
        self.assertEqual(self.bake(run), 0)
        self.assertEqual(run.calls, [])
        self.assertEqual((self.dir / "+48+011_water.osm.bz2").read_bytes(), b"old")

    def test_only_missing_layers_are_baked(self):
        self.fill(["water"])
        self.assertEqual(self.bake(FakeOsmium()), 4)
        self.assertEqual((self.dir / "+48+011_water.osm.bz2").read_bytes(), b"old")

    def test_failure_on_a_later_layer_leaves_the_old_set_untouched(self):
        self.fill(LAYERS)

        class Boom(FakeOsmium):
            def __call__(self, argv, **kw):
                if "w/natural=coastline" in argv:
                    raise RuntimeError("osmium failed")
                return super().__call__(argv, **kw)

        with self.assertRaises(RuntimeError):
            self.bake(Boom(), force=True)
        for l in LAYERS:
            self.assertEqual((self.dir / f"+48+011_{l}.osm.bz2").read_bytes(), b"old")
        self.assertEqual(list(self.out.rglob("*.part")), [])

    def test_force_overwrites(self):
        self.fill(LAYERS)
        self.assertEqual(self.bake(FakeOsmium(), force=True), 5)
        self.assertNotEqual((self.dir / "+48+011_water.osm.bz2").read_bytes(), b"old")


POLY = "england\n1\n 0.0 50.0\n 0.0 54.0\n 10.0 54.0\n 10.0 50.0\n 0.0 50.0\nEND\nEND\n"
L_POLY = "l\n1\n 0 0\n 0 3\n 1.5 3\n 1.5 1.5\n 3 1.5\n 3 0\n 0 0\nEND\nEND\n"
HOLE_POLY = ("h\n1\n 0 0\n 0 10\n 10 10\n 10 0\n 0 0\nEND\n"
             "!2\n 4 4\n 4 6\n 6 6\n 6 4\n 4 4\nEND\nEND\n")  # lon lat per line


class Poly(unittest.TestCase):
    def test_tiles_wholly_inside_a_rectangle(self):
        rings = osm_bake.parse_poly(POLY)
        self.assertEqual(len(osm_bake.tiles_inside(rings)), 40)
        self.assertTrue(osm_bake.tile_inside(rings, 50, 0))
        self.assertTrue(osm_bake.tile_inside(rings, 53, 9))
        self.assertFalse(osm_bake.tile_inside(rings, 54, 0))
        self.assertFalse(osm_bake.tile_inside(rings, 50, 10))

    def test_concave_polygon(self):
        rings = osm_bake.parse_poly(L_POLY)
        self.assertTrue(osm_bake.tile_inside(rings, 0, 0))
        self.assertTrue(osm_bake.tile_inside(rings, 2, 0))
        self.assertFalse(osm_bake.tile_inside(rings, 2, 2))  # in the notch

    def test_reflex_vertex_inside_tile_rejects_it(self):
        # the L's reflex vertex (1.5, 1.5) lies inside tile 1,1: three corners
        # are inside the polygon, the fourth is not
        self.assertFalse(osm_bake.tile_inside(osm_bake.parse_poly(L_POLY), 1, 1))

    def test_edge_crossing_without_corner_or_vertex_inside(self):
        # a thin diagonal band crosses a tile; no corner inside the band
        rings = osm_bake.parse_poly("b\n1\n 0 0\n 0 1\n 5 6\n 5 5\n 0 0\nEND\nEND\n")
        self.assertFalse(osm_bake.tile_inside(rings, 2, 2))

    def test_hole_excludes_tiles(self):
        rings = osm_bake.parse_poly(HOLE_POLY)
        self.assertFalse(osm_bake.tile_inside(rings, 4, 4))
        self.assertFalse(osm_bake.tile_inside(rings, 5, 5))
        self.assertTrue(osm_bake.tile_inside(rings, 0, 0))

    def test_negative_longitude(self):
        rings = osm_bake.parse_poly("x\n1\n -4 53\n -4 55\n -2 55\n -2 53\n -4 53\nEND\nEND\n")
        self.assertTrue(osm_bake.tile_inside(rings, 53, -4))
        self.assertTrue(osm_bake.tile_inside(rings, 53, -3))
        self.assertFalse(osm_bake.tile_inside(rings, 53, -2))


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.pbf = d / "gb-261022.osm.pbf"
        self.pbf.write_bytes(b"x")
        self.poly = d / "gb.poly"
        self.poly.write_text(POLY)
        self.out = d / "cache"

    def args(self, *extra):
        return osm_bake.parse_args(["--pbf", str(self.pbf), "--out", str(self.out), *extra])

    def test_args(self):
        a = osm_bake.parse_args(["--pbf", "a.pbf", "--out", "o", "--tile", "48", "11", "--force"])
        self.assertEqual((a.tile, a.force), ([48, 11], True))
        a = osm_bake.parse_args(["--pbf", "a.pbf", "--out", "o", "--poly", "p"])
        self.assertEqual((a.tile, a.force), (None, False))

    def test_without_tile_a_poly_is_required(self):
        with self.assertRaises(SystemExit):
            osm_bake.run_main(self.args(), FakeOsmium())

    def test_tile_outside_poly_is_refused(self):
        run = FakeOsmium()
        with self.assertRaises(SystemExit):
            osm_bake.run_main(self.args("--poly", str(self.poly), "--tile", "60", "0"), run)
        self.assertEqual(run.calls, [])

    def test_single_tile_without_poly_and_provenance_record(self):
        run = FakeOsmium()
        osm_bake.run_main(self.args("--tile", "53", "-3"), run)
        self.assertTrue((self.out / "+50-010" / "+53-003" / "+53-003_water.osm.bz2").exists())
        self.assertEqual(run.calls[0][:2], ["osmium", "fileinfo"])
        self.assertEqual(sum(c[1] == "tags-filter" for c in run.calls), 1 + 5)  # prefilter + layers
        log = (self.out / "osm-bake.log").read_text().splitlines()
        self.assertEqual(len(log), 1)
        tile, extract, pbf, baked = log[0].split("\t")
        self.assertEqual((tile, extract, pbf), ("+53-003", "2026-10-22T20:21:02Z", "gb-261022.osm.pbf"))

    def test_poly_run_bakes_every_tile_inside(self):
        run = FakeOsmium()
        osm_bake.run_main(self.args("--poly", str(self.poly)), run)
        self.assertEqual(sum(c[1] == "extract" for c in run.calls), 40)
        self.assertEqual(len((self.out / "osm-bake.log").read_text().splitlines()), 40)

    def test_no_log_line_when_a_worker_filled_the_tile_meanwhile(self):
        out = self.out

        class WorkerFills(FakeOsmium):
            def __call__(self, argv, **kw):
                r = super().__call__(argv, **kw)
                if argv[1] == "tags-filter" and "nwr/aeroway" in argv and "w/natural=coastline" in argv:
                    for l in LAYERS:  # the worker publishes while the prefilter runs
                        p = osm_bake.layer_path(out, 53, -3, l)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(b"worker")
                return r

        osm_bake.run_main(self.args("--tile", "53", "-3"), WorkerFills())
        self.assertFalse((self.out / "osm-bake.log").exists())

    def test_nothing_to_do_runs_nothing(self):
        osm_bake.run_main(self.args("--tile", "53", "-3"), FakeOsmium())
        run2 = FakeOsmium()
        osm_bake.run_main(self.args("--tile", "53", "-3"), run2)
        self.assertEqual(run2.calls, [])
        self.assertEqual(len((self.out / "osm-bake.log").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
