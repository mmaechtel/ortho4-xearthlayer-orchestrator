import unittest
from math import floor
from pathlib import Path

PATCHES = Path(__file__).resolve().parents[1] / "patches"


def block_of(tile):
    lat, lon = int(tile[:3]), int(tile[3:])
    return f"{floor(lat / 10) * 10:+03d}{floor(lon / 10) * 10:+04d}"


class PatchesLayout(unittest.TestCase):
    def test_every_patch_sits_in_its_tiles_block(self):
        problems = []
        for entry in sorted(PATCHES.rglob("*")):
            rel = entry.relative_to(PATCHES)
            if entry.is_dir():
                if len(rel.parts) == 2 and block_of(rel.parts[1]) != rel.parts[0]:
                    problems.append(f"{rel}: block should be {block_of(rel.parts[1])}")
                continue
            if len(rel.parts) != 3 or not rel.name.endswith(".patch.osm"):
                problems.append(f"{rel}: expected <block>/<tile>/<file>.patch.osm")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
