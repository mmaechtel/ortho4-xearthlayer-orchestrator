import json
import os
from fake_log import enter, rec, ret
import O4_File_Names as FNAMES
import O4_Overlay_Utils as OVL


def build_poly_file(tile):
    enter("build_poly_file")
    rec("cfg overlay_src=" + OVL.custom_overlay_src)
    rec("tileattrs " + json.dumps({k: v for k, v in vars(tile).items() if k not in ("lat", "lon")}, sort_keys=True))
    # OSM layers as Ortho4XP finds them, then the ones it "downloads"
    # (FAKE_O4_OSM_DOWNLOAD, comma-separated file names).
    d = FNAMES.osm_dir(tile.lat, tile.lon)
    rec("osm-present " + ",".join(sorted(os.listdir(d)) if os.path.isdir(d) else []))
    for name in filter(None, os.environ.get("FAKE_O4_OSM_DOWNLOAD", "").split(",")):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w") as f:
            f.write("downloaded")
    return ret("build_poly_file")
