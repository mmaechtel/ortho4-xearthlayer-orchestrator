# Own XEarthLayer packages with OXO — target state and migration

**Date:** 2026-10-23
**Scope:** make OXO the way the operator builds their own ortho packages for
XEarthLayer, reusing the legacy Ortho4XP patch tree and Sonny's elevation data,
while every package built so far stays installed and in use.

This plan is deliberately small. OXO already produces exactly the per-tile
directory the operator's packaging step consumes; what is missing is wiring
(mounts, a house profile, one packaging switch), not software.

## What exists today (findings)

| Area | Legacy (as found) | OXO (as found) |
|---|---|---|
| Ortho4XP | `/mnt/xplane_data/docker/Ortho4XP`, fork of Shred86 v1.40.13; only `src/O4_OSM_Utils.py` differs (weighted Overpass server choice). Side modules `apt_compat_patch.py`, `dem_lock_patch.py` are monkeypatches. | Image clones Shred86 at a pinned commit (`worker/Containerfile:8-17`). |
| Build patches | `Patches/<10° block>/<tile>/*.patch.osm` — 176 files, upstream layout, read by Ortho4XP natively. Second copy in `OrthoForge/Patches`. | Read-only mount at `/var/oxo/patches-active`, same block-nested layout, always on (`worker/README.md:24-29`). |
| Elevation | `Global Elevation Data by MM/` — 62 GB, 7795 flat `N48E011.hgt` (1″ Sonny/viewfinder). `Elevation_data/<block>` are 629 relative symlinks onto it. Read by Ortho4XP's stock `View` source (`O4_File_Names.base_file_name` → `Elevation_data/<block>/N..E...hgt`); `custom_dem` is empty. | `Elevation_data` → `/var/oxo/dem` (dem-cache hostPath). No Sonny wiring. |
| House settings | BI, ZL17, `mesh_zl=19`, `curvature_tol=2.0`, `min_angle=10`, `cover_airports_with_highres=ICAO`, `cover_zl=18`, `cover_extent=6`, `masking_mode=rocks` (regional EU: `sand`), `mask_zl=16`, `water_tech=XP12`, `road_level=3`, `fill_nodata=True`; app: `overpass_server_choice=DE`. | Spec sets `provider`, `zoom`, `include_overlays`; every other tile key via `[parameters.raw]`; app keys via `OXO_O4_APP_OVERRIDES`. |
| Packaging | `xearthlayer-config/bin/sync-xel-package <name>` copies `done` tiles from a build dir (`zOrthos_<name>/zOrtho4XP_*` + `build_status.tsv`) into `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`, validates (`--strict`: BI cfg, DSF ≥10 KB, `.ter` → `_BI<zl>.dds`, mask PNG), writes `xearthlayer_scenery_package.txt` with a priority code. `xearthlayer-publish` is not used for own packages. | Egress commits a whole `zOrtho4XP_<tile>/` atomically into `target.root` (`oxo-worker/src/exec.rs:228-268`) — same shape as a legacy build dir, cfg included. |
| Coexistence | Lowest priority code wins **per file**; own packages sit at `A5_<REG>`; runtime XEL patches (94 addon symlinks, `PATCHES.md`) beat everything. | — |

Two different things are called "patches": the **build patches** (`.patch.osm`,
input to Ortho4XP — this plan) and the **XEL runtime patches** (addon symlinks
in `~/.local/share/xearthlayer/patches` — untouched by this plan).

## Target state

```
region spec (TOML: tiles + house profile)
   │ POST /api/v1/jobs
   ▼
oxo-controld ── persistent PostgreSQL
   ▲ claim/report (HTTP)
   │
worker pods (oxo-worker image, stock Shred86 Ortho4XP)
   mounts: patches-active ← /mnt/xplane_data/docker/Ortho4XP/Patches   (ro)
           dem            ← /mnt/xplane_data/oxo/dem-links            (symlink dir)
           dem-sonny      ← …/docker/Ortho4XP/Global Elevation Data by MM (ro)
           artifacts      ← /mnt/xplane_data/Orthos/Ortho4XP          (target.root = …/zOrthos_<package>)
   ▼
/mnt/xplane_data/Orthos/Ortho4XP/zOrthos_<package>/zOrtho4XP_<tile>/
   │ sync-xel-package <package> --strict      (no build_status.tsv → all present tiles)
   ▼
~/.local/share/xearthlayer/packages/zzXEL_<package>_ortho/   (priority code A5_<REG>)
```

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | **Stock Shred86 Ortho4XP, no fork.** The image's pinned commit stays. | The fork's only source change is Overpass server weighting; `overpass_server_choice=DE` via app overrides is enough. `apt_compat_patch` only matters for OrthoForge `.apt` pickles in a shared OSM cache, which OXO pods don't have. `dem_lock_patch` guards concurrent DEM downloads, which D3 rules out. |
| D2 | **Mount the legacy build-patch tree read-only, as is.** `/mnt/xplane_data/docker/Ortho4XP/Patches` stays the single source of truth; patches keep being edited there. | Layout already matches the pod contract. No copy, no drift. |
| D3 | **Sonny via stock `View` source, through an OXO-owned symlink dir.** A one-off script creates `/mnt/xplane_data/oxo/dem-links/<block>` → `/var/oxo/dem-sonny` (absolute, valid inside the pod) for all 629 blocks; the 62 GB tree is mounted read-only at `/var/oxo/dem-sonny`. No `custom_dem`. | Zero data movement; legacy `Elevation_data` keeps working untouched. Read-only means a tile without Sonny coverage fails loudly instead of silently building on downloaded non-Sonny data — and no concurrent writes means no download race. |
| D4 | **House profile = spec parameters**, overlays off (`include_overlays = false`; own packages never carried overlays). Variants that differ in a tile key (e.g. `masking_mode` rocks vs sand) are separate specs. | Matches the spec model; no per-tile Köppen logic in OXO. |
| D5 | **Packaging stays in `xearthlayer-config`, OXO writes into the existing build-dir convention.** `target.root` is `/mnt/xplane_data/Orthos/Ortho4XP/zOrthos_<package>`, where `sync-xel-package` already looks. When that directory has no `build_status.tsv`, every `zOrtho4XP_*` present counts as done (egress is atomic, `oxo-worker/src/exec.rs:258`); the existing `--strict` validation still decides. About five lines in `bin/sync-xel-package:115`. The sync also refuses to run while `xearthlayer run` serves the packages: the PID in `~/.local/state/xearthlayer/xearthlayer.lock` is alive (`kill -0`) — the same check XEL's own installer makes. | Reuses the proven validator and metadata writer; no new flag or path argument; OXO does not learn about XEarthLayer packages. |
| D6 | **Old packages stay exactly as they are.** New OXO packages get their own `zzXEL_<name>_ortho` directory and code. An old region is replaced only deliberately, later, by giving the OXO package the same code and removing the old directory after a check. | Per-file priority makes accidental shadowing the main risk; separate dirs and explicit codes keep it visible. |
| D7 | **Operations without new code:** persistent PostgreSQL as a named-volume Podman container; `oxo-controld --bind 0.0.0.0:8080`; worker `OXO_CONTROL_URL` = host IP; `OXO_MIN_FREE_SCRATCH_BYTES` ≥ 16 GiB for ZL17. Jobs are submitted with `curl`; the console (sub-project 5) is not a prerequisite. | Everything needed exists; `make pg-up` is disposable and unfit for production state. |

## Rejected alternatives

- **Packaging through XEarthLayer's own package path** (`xearthlayer-publish add → build → urls → version --bump → release`, a local HTTP server for the library — XEL fetches libraries over HTTP only, `xearthlayer/src/manager/cache.rs` — an extra `library_url`, then `xearthlayer packages install`). Custom region codes such as `A5_EU` would be accepted. Rejected for now: about six steps plus a running server per package, archives packed and unpacked again (double disk and time at hundreds of tiles), and no incremental top-up during a build (`auto-sync-package`). What it would add — versions, checksums, update display, refusal to replace a package while `run` serves it — matters only once packages are shared with others. It can be added later on the same `zOrthos_<package>` build dir without touching OXO. The one safety property worth having now is taken over cheaply in D5.

## Out of scope

- Rebuilding existing packages with OXO (only on demand, region by region, per D6).
- `xearthlayer-publish` and any public release.
- Overlays in own packages.
- Bounding-box tile authoring in OXO (tile lists come from `xearthlayer-config`, see M3).
- Pointing OXO straight at an XEarthLayer directory. Rejected: a package needs the merged layout (`Earth nav data/`, flat `terrain/`, `textures/`) plus `xearthlayer_scenery_package.txt`, which per-tile egress does not produce; the XEL patches directory does accept whole `zOrtho4XP_*` tiles (`xearthlayer/src/config/settings.rs:255`) but outranks every package, airports included, which breaks the priority ladder.
- The texture-bytes sanity floor (deferred in the worker design); `sync-xel-package --strict` is the gate meanwhile.

## Migration

### M0 — Checks (read-only, half a day)

1. Confirm the image's pinned Shred86 commit has the same `O4_File_Names.base_file_name` / `elevation_data("View")` behaviour as legacy v1.40.13 (it is the stock lookup D3 relies on).
2. `diff -r` `docker/Ortho4XP/Patches` against `OrthoForge/Patches`; settle on the docker copy (D2) and note any file only in OrthoForge.
3. Coverage check for the pilot tiles: each has `Global Elevation Data by MM/<N..E...>.hgt`.

### M1 — Wiring (OXO repo + host)

1. Script `make-oxo-dem-links.py` (in `xearthlayer-config/bin/`, host deployment concern) creates `/mnt/xplane_data/oxo/dem-links`.
2. `deploy/worker-pod.yaml`: add an optional, commented `dem-sonny` read-only volume; `worker/README.md`: one paragraph that the dem-cache may hold symlinks into additional read-only mounts. Operator's edited copy sets the four hostPaths plus `dem-sonny`.
3. House-profile example spec `deploy/specs/house-profile.example.toml` (D4 values).
4. Persistent PostgreSQL container and the `oxo-controld` invocation, written down in `deploy/README` (or as a section in `worker/README.md`).

### M2 — Pilot (compare against legacy)

1. Spec with 2–3 tiles that already exist in `zzXEL_eu_sonny_ortho` (e.g. `+48+011`), house profile, `target.root = /mnt/xplane_data/Orthos/Ortho4XP/zOrthos_oxo_pilot`.
2. Run one worker pod; job reaches `complete`.
3. `sync-xel-package oxo_pilot --strict` with code `A4_PILOT` (outranks `A5_EU` per file).
4. Compare against the legacy tiles: DSF size/triangle count, `.ter` names, masks, Sonny terrain visibly used; fly over in the sim.
5. Remove the pilot package. Exit criterion: equivalent tiles, no manual step outside this plan.

### M3 — First real package

1. Pick a region not yet built (no overlap with any `custom`/`apt` package — the `add-tiles` filter already knows how). Generate the `tiles = [...]` list from that filter (small helper next to `add-tiles`).
2. Run with several worker pods; sync into `zzXEL_<name>_ortho` with a new `A5_<REG>` code added to the mapping in `sync-xel-package`.

### M4 — Steady state

- New own packages are built only with OXO; the legacy Ortho4XP install is frozen, not deleted (it still owns `Elevation_data` and the patch tree the pods mount).
- `xearthlayer-config` skills follow: `build-workers` → start/scale OXO worker pods and submit specs; `add-tiles` → emits spec tile lists; `sync-xel-package` / `auto-sync-package` work unchanged on OXO build dirs (no TSV). `check-custom-scenery`, `check-done-tiles`, `check-ortho-cfg` stay as they are.

## Changes by repository

| Repo | Change | Size |
|---|---|---|
| OXO | optional `dem-sonny` volume in `deploy/worker-pod.yaml`, README paragraph, example house-profile spec, persistent-Postgres/controld run notes | docs/config only, no Rust |
| xearthlayer-config | `sync-xel-package` TSV-less fallback and `run`-lock refusal, new code mapping entry, `make-oxo-dem-links.py`, tile-list helper, skill updates | small scripts |
| Legacy Ortho4XP | none | — |

## Open decisions

- Priority code for the pilot (`A4_PILOT` proposed) and naming of the first OXO region package.
- Which region is the first real package (M3).
