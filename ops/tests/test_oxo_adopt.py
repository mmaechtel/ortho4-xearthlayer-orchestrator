import importlib.machinery
import importlib.util
import struct
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "oxo-adopt"
loader = importlib.machinery.SourceFileLoader("oxo_adopt", str(SCRIPT))
spec = importlib.util.spec_from_loader("oxo_adopt", loader)
oxo_adopt = importlib.util.module_from_spec(spec)
loader.exec_module(oxo_adopt)


def atom(aid, payload):
    return aid[::-1].encode() + struct.pack("<I", 8 + len(payload)) + payload


def strings(*items):
    return b"".join(s.encode() + b"\0" for s in items)


def dsf_bytes(agent, ters):
    head = atom("HEAD", atom("PROP", strings("sim/west", "11", "sim/creation_agent", agent)))
    defn = atom("DEFN", atom("TERT", strings("terrain_Water", *ters)))
    body = head + defn
    return b"XPLNEDSF" + struct.pack("<I", 1) + body + b"\0" * 16


TER = """A
800
TERRAIN

BASE_TEX_NOWRAP ../textures/{rc}_{pz}.dds
"""
# As Ortho4XP writes them: the mask is referenced only by the sea overlay terrain.
SEA_TER = TER + "BORDER_TEX ../textures/{rc}_ZL{mzl}.png\nWET\n"


def package(root, name="eu_apt", code="A0_EU", tiles=None):
    """A minimal installed XEL package: tiles = {tile: (agent, [(row_col, provzl, mask_zl)])}."""
    pkg = root / f"zzXEL_{name}_ortho"
    (pkg / "terrain").mkdir(parents=True)
    (pkg / "xearthlayer_scenery_package.txt").write_text(
        f"REGIONAL SCENERY PACKAGE\n1.0.0\n{code}  99.99.99\n2026-04-04T00:00:00Z\nZ\nzzXEL_{name}_ortho\n")
    for tile, (agent, ters) in (tiles or {}).items():
        names = []
        for rc, pz, mzl in ters:
            (pkg / "terrain" / f"{rc}_{pz}.ter").write_text(TER.format(rc=rc, pz=pz))
            names.append(f"terrain/{rc}_{pz}.ter")
            if mzl:
                (pkg / "terrain" / f"{rc}_{pz}_sea_overlay.ter").write_text(SEA_TER.format(rc=rc, pz=pz, mzl=mzl))
                names.append(f"terrain/{rc}_{pz}_sea_overlay.ter")
        d = pkg / "Earth nav data" / oxo_adopt.block(tile)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{tile}.dsf").write_bytes(dsf_bytes(agent, names))
    return pkg


def o4_cfg(root, region, tile, website="BI", zl="17", extra=""):
    d = root / "Ortho4XP" / "src" / "EU" / region / f"zOrtho4XP_{tile}"
    d.mkdir(parents=True)
    (d / f"Ortho4XP_{tile}.cfg").write_text(
        f"mesh_zl=18\r\nmasking_mode=rocks\r\ncustom_dem=\r\n{extra}default_website={website}\r\ndefault_zl={zl}\r\n")


def os_cfg(root, tile, provider="BI", zl=16):
    d = root / "OrthoStudio" / "tiles" / f"zOrthoStudio_{tile}"
    d.mkdir(parents=True)
    (d / "tile_settings.cfg").write_text("mesh_zl=18\nmasking_mode=3steps\n")
    (d / "orthostudio.toml").write_text(f'[tile]\nname = "{tile}"\nprovider = "{provider}"\nzl = {zl}\n')


class ReadDsf(unittest.TestCase):
    def test_reads_creation_agent_and_terrain_names(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "x.dsf"
            f.write_bytes(dsf_bytes("Ortho4XP 1.40", ["terrain/1_2_BI16.ter"]))
            props, ters = oxo_adopt.read_dsf(f)
            self.assertEqual(props["sim/creation_agent"], "Ortho4XP 1.40")
            self.assertEqual(ters, ["terrain_Water", "terrain/1_2_BI16.ter"])

    def test_reads_a_7z_compressed_dsf(self):
        with tempfile.TemporaryDirectory() as t:
            raw = Path(t) / "+48+011.dsf"
            raw.write_bytes(dsf_bytes("osxp", ["terrain/1_2_BI18.ter"]))
            subprocess.run(["7z", "a", "-bso0", str(Path(t) / "a.7z"), str(raw)], check=True)
            packed = Path(t) / "packed.dsf"
            packed.write_bytes((Path(t) / "a.7z").read_bytes())
            props, ters = oxo_adopt.read_dsf(packed)
            self.assertEqual(props["sim/creation_agent"], "osxp")
            self.assertIn("terrain/1_2_BI18.ter", ters)


class Observe(unittest.TestCase):
    def test_counts_textures_per_provider_and_zl_and_collects_mask_zls(self):
        with tempfile.TemporaryDirectory() as t:
            pkg = package(Path(t), tiles={"+48+011": ("osxp", [
                ("1_2", "BI16", 16), ("1_3", "BI16", 16), ("5_6", "BI18", 18), ("5_7", "BI18", None)])})
            obs = oxo_adopt.observe(pkg, "+48+011")
            self.assertEqual(obs["creation_agent"], "osxp")
            self.assertEqual(obs["textures"], {"BI16": 2, "BI18": 2})
            self.assertEqual(obs["mask_zl"], [16, 18])
            self.assertGreater(obs["dsf_bytes"], 0)

    def test_provider_names_with_digits(self):
        self.assertEqual(oxo_adopt.provzl("terrain/1_2_GO218_sea_overlay.ter"), ("GO2", 18))
        self.assertEqual(oxo_adopt.provzl("terrain/1_2_BI16.ter"), ("BI", 16))
        self.assertIsNone(oxo_adopt.provzl("terrain_Water"))


class ChooseCfg(unittest.TestCase):
    OBS = {"textures": {"BI17": 10, "BI18": 3}}

    def test_cfg_agreeing_with_observed_provider_and_base_zl_is_taken(self):
        with tempfile.TemporaryDirectory() as t:
            o4_cfg(Path(t), "APT", "+48+011", "BI", "17")
            status, source, values = oxo_adopt.choose_cfg(oxo_adopt.candidates(Path(t), "+48+011"), self.OBS)
            self.assertEqual(status, "agrees")
            self.assertIn("EU/APT/zOrtho4XP_+48+011", source)
            self.assertEqual(values["masking_mode"], "rocks")
            self.assertNotIn("custom_dem", values)  # empty values carry nothing

    def test_cfg_with_other_base_zl_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            o4_cfg(Path(t), "CENTER", "+48+011", "BI", "16")
            status, source, values = oxo_adopt.choose_cfg(oxo_adopt.candidates(Path(t), "+48+011"), self.OBS)
            self.assertEqual((status, source, values), ("rejected", None, {}))

    def test_no_candidate_is_none(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(oxo_adopt.choose_cfg(oxo_adopt.candidates(Path(t), "+48+011"), self.OBS),
                             ("none", None, {}))

    def test_two_agreeing_cfgs_with_different_values_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as t:
            o4_cfg(Path(t), "APT", "+48+011", "BI", "17")
            o4_cfg(Path(t), "CENTER", "+48+011", "BI", "17", extra="road_level=3\n")
            status, _, values = oxo_adopt.choose_cfg(oxo_adopt.candidates(Path(t), "+48+011"), self.OBS)
            self.assertEqual((status, values), ("ambiguous", {}))

    def test_orthostudio_takes_provider_and_zl_from_its_toml(self):
        with tempfile.TemporaryDirectory() as t:
            os_cfg(Path(t), "+48+011", "BI", 16)
            status, source, values = oxo_adopt.choose_cfg(
                oxo_adopt.candidates(Path(t), "+48+011"), {"textures": {"BI16": 4, "BI18": 1}})
            self.assertEqual(status, "agrees")
            self.assertIn("zOrthoStudio_+48+011", source)
            self.assertEqual((values["default_website"], values["default_zl"]), ("BI", "16"))


class Adopt(unittest.TestCase):
    def test_writes_one_record_per_package_with_origins(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            pkg = package(root / "packages", tiles={
                "+48+011": ("Ortho4XP 1.40", [("1_2", "BI17", 17), ("5_6", "BI18", 18)]),
                "+47+011": ("osxp", [("3_4", "BI16", 16)]),
            })
            o4_cfg(root / "orthos", "APT", "+48+011", "BI", "17")
            out = oxo_adopt.adopt(pkg, root / "orthos", root / "adopted", now="2026-10-23T12:00:00Z")
            self.assertEqual(out, root / "adopted" / "eu_apt.toml")
            rec = tomllib.loads(out.read_text())
            self.assertEqual(rec["package"]["name"], "eu_apt")
            self.assertEqual(rec["package"]["code"], "A0_EU")
            self.assertEqual(rec["package"]["adopted"], "2026-10-23T12:00:00Z")
            a = rec["tiles"]["+48+011"]
            self.assertEqual(a["observed"]["textures"], {"BI17": 1, "BI18": 1})
            self.assertEqual(a["cfg_status"], "agrees")
            self.assertEqual(a["cfg"]["mesh_zl"], "18")
            b = rec["tiles"]["+47+011"]
            self.assertEqual(b["cfg_status"], "none")
            self.assertNotIn("cfg", b)

    def test_package_name_must_follow_the_xel_layout(self):
        with tempfile.TemporaryDirectory() as t:
            bad = Path(t) / "somewhere"
            bad.mkdir()
            with self.assertRaises(oxo_adopt.AdoptError):
                oxo_adopt.adopt(bad, Path(t), Path(t) / "adopted")


if __name__ == "__main__":
    unittest.main()
