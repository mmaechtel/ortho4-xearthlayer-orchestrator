# ops — own XEarthLayer packages on this host

Fork-only operator material (branch `ops`). Everything needed to go from a
region spec to an installed XEarthLayer package lives here or under
`/mnt/xplane_data/oxo/`; nothing reads the legacy Ortho4XP install.
Why it looks like this: `docs/plans/2026-10-23-own-package-production.md`.

| Path | What |
|---|---|
| `ops/patches/<block>/<tile>/*.patch.osm` | Ortho4XP build patches, mounted read-only into every worker. Edit and commit here. |
| `ops/packages/<package>.toml` | One file per package: metadata, target, tile groups with per-group overrides. |
| `ops/profiles/house.toml` | Our few deliberate deviations from samsoir's settings. |
| `ops/bin/oxo-compose` | Baseline (`docs/examples/example-region.toml`, samsoir) + house + package → one spec per group; prints, writes or submits. |
| `ops/worker-pod.yaml` | Worker pod with this host's paths; `worker-pod-2..6.yaml` are its copies for workers 2–6. |
| `ops/bin/import-dem` | Flat `.hgt` → `Elevation_data` layout (btrfs reflinks). |
| `ops/bin/osm-bake` | Geofabrik `.osm.pbf` → per-tile OSM layers in the OSM cache (needs `osmium-tool`), see below. |
| `ops/bin/osm-fetch` | Geofabrik extracts: download + MD5 check + ledger line (`ops/ledger/osm-extracts.tsv`), `--check` for newer ones, `--which TILE...` for the region covering a tile; also the pre-build check behind `oxo-compose --submit`, see below. |
| `ops/bin/oxo-package` | Delivered tiles → `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`. Night lighting (#17): each tile's land `.ter` get the `TEXTURE_LIT`/`LUMINANCE` lines of the installed package that holds the tile's `night/<block>/<tile>.oxn` (same `<y>_<x>` and ZL; no counterpart → the tile's value if unanimous); the recipe stays in that package so XEL colours the LEDs by its region. `--dry-run` prints the plan. |
| `ops/ledger/<package>/` | The books: one `<region_code>-r<rev>.toml` per submitted job, `installs.log`, `night.tsv` (per install and tile: night source package, its code line, lit `.ter`, LUMINANCE, warnings). Committed. |
| `ops/bin/oxo-whence <tile>` | How a tile was built: builds newest first, commits, DEM, patches, deviations from samsoir, installs; last the adoption record. A ledger entry's `[provenance.built]` (shown as "built with:") records what differed at build time from the submit-time provenance. |
| `ops/bin/oxo-adopt <zzXEL dir>` | Records an own legacy package once as it is installed (`ops/adopted/<name>.toml`): provider/ZL/masks/creation agent per tile *observed* from the files, a legacy tile cfg only if it agrees with them. Committed. |
| `ops/console/` | Read-only web console (band + tile map): `python3 ops/console/server.py`, then http://127.0.0.1:8090/. |
| `/mnt/xplane_data/oxo/dem/` | Sonny/viewfinder DEMs, Ortho4XP layout, mounted read-only. |
| `/mnt/xplane_data/oxo/artifacts/<package>/` | Delivered `zOrtho4XP_<tile>/` dirs (spec `target.root`). |
| `~/X-Plane-12/Global Scenery/` | Mounted read-only as the pod's `content`: every ortho DSF takes its DEM and bathymetry rasters from the matching Global Scenery DSF. |

Tests for the scripts: `python3 -m unittest discover -s ops/tests`.

## One-time setup

```sh
# Podman (Debian 13)
pkexec /usr/bin/apt-get install -y podman
# Pillow for oxo-package (merges masks that neighbouring tiles share)
pkexec /usr/bin/apt-get install -y python3-pil

# DEMs (already done 2026-10-23; rerunnable, copies only what is missing)
ops/bin/import-dem "/mnt/xplane_data/docker/Ortho4XP/Global Elevation Data by MM" /mnt/xplane_data/oxo/dem
mkdir -p /mnt/xplane_data/oxo/artifacts

# Persistent PostgreSQL (not `make pg-up`, which is disposable)
podman volume create oxo-pg
podman run -d --name oxo-pg --restart=always -v oxo-pg:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=oxo -p 127.0.0.1:55433:5432 docker.io/library/postgres:17-alpine

# Worker image
make image
```

## Producing a package

```sh
# 1. Control plane. 0.0.0.0 so pods reach it via host.containers.internal;
#    the API has no auth — keep the port off untrusted networks.
#    As a user unit, so it outlives the terminal (logs: journalctl --user -u oxo-controld;
#    stop: systemctl --user stop oxo-controld).
cargo build --release -p oxo-controld
systemd-run --user --unit oxo-controld --property=Restart=on-failure \
  "$PWD/target/release/oxo-controld" \
  --database-url postgres://postgres:oxo@127.0.0.1:55433/postgres --bind 0.0.0.0:8080

# 2. Package file: copy ops/packages/oxo_pilot.toml, set metadata (own
#    region_code), target.root = /mnt/xplane_data/oxo/artifacts/<name>, groups.
mkdir -p /mnt/xplane_data/oxo/artifacts/<name>
ops/bin/oxo-compose ops/packages/<name>.toml            # inspect the composed specs
ops/bin/oxo-compose ops/packages/<name>.toml --out /tmp/specs && \
  for f in /tmp/specs/*.toml; do cargo run -q -p oxo-spec-cli -- validate "$f"; done

# 3. Submit, one job per group. A job is identified by (region_code, revision):
#    resubmitting the same pair returns the existing job if the planned tasks,
#    max_attempts/backoff_seconds and the worker payload (oxo-control/src/planner.rs
#    WorkerPayload) are unchanged, else 409. metadata.name and alert destinations
#    are not compared. Bump revision to rebuild or change anything.
#    Refuses with uncommitted changes in ops/ (the ledger must name a real commit).
git add ops/packages/<name>.toml && git commit -m "ops: package <name>"
ops/bin/oxo-compose ops/packages/<name>.toml --submit http://127.0.0.1:8080
git add ops/ledger && git commit -m "ledger: submit <name>"

# 4. Workers. Up to six: ops/worker-pod-2.yaml .. -6.yaml differ only in metadata.name
#    AND the scratch volume name (scratch-N): podman shares same-named emptyDir
#    volumes between pods, and the workers wipe each other's builds.
podman kube play ops/worker-pod.yaml
for n in 2 3 4 5 6; do podman kube play ops/worker-pod-$n.yaml; done
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>              # complete / failed / in_progress
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>/throughput
podman logs -f oxo-worker-1-worker

# 5. Package (refuses while `xearthlayer run` is serving)
ops/bin/oxo-package ops/packages/<name>.toml --code A5_<REG> --dry-run
ops/bin/oxo-package ops/packages/<name>.toml --code A5_<REG>
git add ops/ledger && git commit -m "ledger: install <name>"

# Later: how was a tile built?
ops/bin/oxo-whence +48+011

podman kube down ops/worker-pod.yaml   # and ops/worker-pod-N.yaml
```

## Baking OSM layers locally

Instead of waiting on Overpass, bake the five layers per tile from a Geofabrik extract (needs `osmium-tool`; download `<region>.osm.pbf` and `<region>.poly` yourself):

```sh
# every tile wholly inside the extract's .poly (border tiles need a larger extract)
ops/bin/osm-bake --pbf great-britain-261022.osm.pbf --poly great-britain.poly --out /mnt/xplane_data/oxo/osm-cache
# one tile (without --poly it is baked as asked); --force overwrites existing layers
ops/bin/osm-bake --pbf ... --out ... --tile 53 -3
```

Existing layers are skipped. `osm-cache/osm-bake.log` gets one line per baked tile: tile, extract timestamp (from the PBF header), PBF name, bake time.

## Fetching extracts and the pre-build OSM check

```sh
ops/bin/osm-fetch great-britain       # or us/texas: .osm.pbf + .poly into /mnt/xplane_data/oxo/osm-pbf, MD5-verified
ops/bin/osm-fetch --check             # per ledger region: local vs. Geofabrik timestamp, newer extract or not (no download)
ops/bin/osm-fetch --which +53-003 +49+006   # smallest Geofabrik region wholly containing each tile
```

The file is named `<region>-<YYMMDD>.osm.pbf` after the PBF header's `osmosis_replication_timestamp`. `ops/ledger/osm-extracts.tsv` (committed, no header) gets one tab-separated line per fetch: region id, file, replication timestamp, md5, fetched at (UTC). Freshness comes from `<region>-updates/state.txt`, not from the `-latest` redirect. Geofabrik's `index-v1.json` is cached next to the PBFs for a day. "Smallest" is by polygon area in square degrees, so the answer can be a region other than the one you have fetched (`united-kingdom` before `great-britain`); the check below prefers an extract already in the ledger.

Before anything is posted, `oxo-compose … --submit` checks every tile of the specs being submitted and refuses (`--osm-check` runs only the check, exit 1 on failure; `--force` submits anyway):

- all five layers exist in `/mnt/xplane_data/oxo/osm-cache`, and
- `osm-bake.log` has an entry for the tile (newest line wins) whose extract timestamp is at most 90 days old. No entry or an `unknown` timestamp counts as outdated — that is every tile copied from the old disk and everything workers fetched from Overpass.

Each failing tile is listed with its reason, followed by the fix: `osm-fetch <region>` when no fresh extract on disk covers it, then `osm-bake --pbf … --tile LAT LON --force`. A re-bake always takes the whole tile (all five layers together), so one tile never mixes Overpass and Geofabrik layers. Offline, the reasons still come out, without the commands.

## Settings: three layers

1. **samsoir's baseline** — `docs/examples/example-region.toml`, read from upstream, never copied.
   Decided 2026-10-23: follow it closely (tuned for streaming performance): ZL16 everywhere,
   airports ZL18 (`cover_zl`).
2. **house** — `ops/profiles/house.toml`: only deliberate deviations, each with a reason
   (BI, no overlays, `cover_extent` 1 km). The legacy values are listed there, not used.
3. **package / group** — `ops/packages/<name>.toml`: whatever differs per package or per set
   of tiles, e.g. `raw = { masking_mode = "sand", masks_width = "25" }` for a coastal group.
   Ortho4XP's `masking_mode` is `sand`, `rocks` or `3steps`; the first two take a single
   `masks_width`, `3steps` a list `[a,b,c]`.

## Priority codes

XEarthLayer resolves per file, lowest code (byte order) wins; patches beat
every package. Own ortho packages sit at `A5_<REG>`, airports at `A0_*`,
base regions below. A code that sorts before an existing package's overrides
it wherever both have the same file — choose deliberately. Existing legacy
packages (`zzXEL_*`) stay as they are.
