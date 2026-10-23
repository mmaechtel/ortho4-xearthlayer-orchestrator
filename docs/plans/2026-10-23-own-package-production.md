# Own XEarthLayer packages with OXO — target state and migration

**Date:** 2026-10-23 (revised the same day: standalone)
**Scope:** make this repository (the operator's fork) the one place that
produces the operator's own ortho packages for XEarthLayer — from region spec
to installed package — with no runtime dependency on the legacy Ortho4XP
installation (`/mnt/xplane_data/docker/Ortho4XP`), on OrthoForge, or on the
build tooling in `xearthlayer-config`. Every package built so far stays
installed and in use.

Deliberately small: OXO already produces exactly the per-tile directory a
package is made from. What is missing is operator data moved into place, a
house profile, one packaging script, and run notes.

## What exists today (findings)

| Area | Legacy (as found) | OXO (as found) |
|---|---|---|
| Ortho4XP | `/mnt/xplane_data/docker/Ortho4XP`, fork of Shred86 v1.40.13; only `src/O4_OSM_Utils.py` differs (weighted Overpass server choice). Side modules `apt_compat_patch.py`, `dem_lock_patch.py` are monkeypatches. | Image clones Shred86 at `c363134` = `v1.40.13-9` (`worker/Containerfile:8-17`). DEM code byte-identical to legacy (M0). |
| Build patches | `Patches/<10° block>/<tile>/*.patch.osm` — 176 files ≈ 30 MB, upstream layout, read by Ortho4XP natively. Identical copy in `OrthoForge/Patches`. One unrelated 223 MB `.raw` (Alaska). | Read-only mount at `/var/oxo/patches-active`, same block-nested layout, always on (`worker/README.md:24-29`). |
| Elevation | `Global Elevation Data by MM/` — flat, 52 GB `.hgt`: 1290 at 1″ (Sonny), 6505 at 3″; Europe bbox 991 × 1″, 224 × 3″. `Elevation_data/<block>` are relative symlinks onto it. Read by Ortho4XP's stock `View` source (`Elevation_data/<block>/N48E011.hgt`); `custom_dem` empty. | `Elevation_data` → `/var/oxo/dem` (dem-cache hostPath). |
| House settings | BI, ZL17, `mesh_zl=19`, `curvature_tol=2.0`, `min_angle=10`, `cover_airports_with_highres=ICAO`, `cover_zl=18`, `cover_extent=6`, `masking_mode=rocks` (regional EU: `sand`), `mask_zl=16`, `water_tech=XP12`, `road_level=3`, `fill_nodata=True`; app: `overpass_server_choice=DE`. | Spec sets `provider`, `zoom`, `include_overlays`; other tile keys via `[parameters.raw]`; app keys via `OXO_O4_APP_OVERRIDES`. |
| Packaging | `xearthlayer-config/bin/sync-xel-package` copies `done` tiles from `zOrthos_<name>/` (+ `build_status.tsv`) into `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`, validates (`--strict`), writes `xearthlayer_scenery_package.txt` (code on line 3, version 99.99.99). | Egress commits a whole `zOrtho4XP_<tile>/` atomically into `target.root` (`oxo-worker/src/exec.rs:228-268`), tile cfg included. |
| Coexistence | Lowest priority code wins **per file**; own packages at `A5_<REG>`; XEL runtime patches (addon symlinks, `PATCHES.md`) beat everything. | — |

Two different things are called "patches": **build patches** (`.patch.osm`,
Ortho4XP input — moved into this repo) and **XEL runtime patches** (addon
symlinks in `~/.local/share/xearthlayer/patches`, configured in
`xearthlayer-config` — untouched; they are XEarthLayer configuration, not
production).

## Target state

Everything the production needs is either in this repository or under one
OXO data root on the host. Nothing points into the legacy install.

```
this repo (fork)                           host: /mnt/xplane_data/oxo/
  ops/patches/<block>/<tile>/*.patch.osm     dem/<block>/N48E011.hgt   (Sonny, native Ortho4XP layout)
  ops/specs/<package>.toml                   artifacts/<package>/zOrtho4XP_<tile>/
  ops/worker-pod.yaml                        content/                  (empty; overlays off)
  ops/bin/oxo-package, import-dem            podman volume oxo-pg      (PostgreSQL data)
  ops/README.md (runbook)

ops/specs/<package>.toml ──POST /api/v1/jobs──▶ oxo-controld ── PostgreSQL (oxo-pg)
                                                    ▲ claim/report
worker pods (oxo-worker image, stock Shred86 Ortho4XP)
  patches-active ← <repo>/ops/patches (ro)   dem ← oxo/dem (ro)   artifacts ← oxo/artifacts
      │
      ▼
oxo/artifacts/<package>/zOrtho4XP_<tile>/
      │  ops/bin/oxo-package ops/specs/<package>.toml --code A5_<REG>
      ▼
~/.local/share/xearthlayer/packages/zzXEL_<package>_ortho/
```

The `ops/` directory is fork-only operator material; upstream code paths
(`deploy/`, `worker/`, crates) stay untouched so upstream merges remain clean.

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | **Stock Shred86 Ortho4XP, no fork.** The image's pinned commit stays. | The legacy fork's only source change is Overpass server weighting; `overpass_server_choice=DE` via app overrides is enough. `apt_compat_patch` only matters for OrthoForge `.apt` pickles in a shared OSM cache, which pods don't have. `dem_lock_patch` guards concurrent DEM downloads, which D3 rules out. |
| D2 | **Build patches live in this repo** under `ops/patches/`, in Ortho4XP's block-nested layout, mounted read-only. Imported once from the legacy tree (`*.patch.osm` only, ≈ 30 MB); from then on edited and versioned here. | Standalone, with history. The 223 MB `.raw` is not a patch file and stays behind. |
| D3 | **Sonny DEMs in an OXO-owned directory in native layout.** `/mnt/xplane_data/oxo/dem/<block>/N..E...hgt` as real files, created once by a reflink copy (`cp --reflink=always`, btrfs: no extra space, independent of the legacy files). Mounted read-only as the pod's dem-cache. Stock `View` source, no `custom_dem`, no symlink tricks, no extra volume. | Deleting the legacy install later cannot break OXO. Read-only means a tile without coverage fails loudly instead of silently building on downloaded data, and no concurrent writes means no download race. |
| D4 | **House profile = spec parameters**, one spec file per package in `ops/specs/`, overlays off (`include_overlays = false`). Variants that differ in a tile key (e.g. `masking_mode`) are separate specs. | Specs are the versioned record of what was built and how. |
| D5 | **Packaging script in this repo: `ops/bin/oxo-package`** (Python, with tests). Reads the spec (name, `target.root`), refuses while `xearthlayer run` serves (PID in `~/.local/state/xearthlayer/xearthlayer.lock` alive — the same check XEL's installer makes), validates every tile with the legacy `--strict` rules (BI cfg, DSF ≥ 10 KB, `.ter` → `_BI<zl>.dds`, mask PNG, no partials), copies DSF / `.ter` / mask PNGs (all top-level, as the legacy sync does) into `zzXEL_<package>_ortho/`, writes `xearthlayer_scenery_package.txt` with the given code. Every `zOrtho4XP_*` present counts as done (egress is atomic). | Standalone; the rules are ported, not reinvented. `sync-xel-package` stays in `xearthlayer-config` for the frozen legacy builds only, so the two never need to agree. |
| D6 | **Old packages stay exactly as they are.** New OXO packages get their own `zzXEL_<package>_ortho` and code. An old region is replaced only deliberately, later, by giving the OXO package the same code and removing the old directory after a check. | Per-file priority makes accidental shadowing the main risk. |
| D7 | **Operations without new Rust code:** Podman installed on the host (Debian package); PostgreSQL as a Podman container on the named volume `oxo-pg`; `oxo-controld --bind 0.0.0.0:8080`; worker `OXO_CONTROL_URL = http://host.containers.internal:8080`; artifacts mounted at the same path as on the host so `target.root` is valid for worker and `oxo-package`; one `region_code` per package (jobs are keyed by `region_code` + `revision`); `OXO_MIN_FREE_SCRATCH_BYTES` ≥ 16 GiB for ZL17; app override `overpass_server_choice=DE`. Jobs submitted with `curl`; the console (sub-project 5) is not a prerequisite. All of it written down in `ops/README.md` and `ops/worker-pod.yaml` (real paths, no `EDIT ME`). | Everything needed exists; `make pg-up` is disposable. |

## Rejected alternatives

- **Mounting the legacy patch tree and DEM directory in place** (first version of this plan). Rejected: keeps OXO tied to an installation that is meant to be retired; the relative DEM symlinks also needed an extra mount to resolve.
- **Packaging through XEarthLayer's own package path** (`xearthlayer-publish add → build → urls → version --bump → release`, a local HTTP server for the library — XEL fetches libraries over HTTP only, `xearthlayer/src/manager/cache.rs` — an extra `library_url`, then `xearthlayer packages install`). Custom codes such as `A5_EU` would be accepted. Rejected for now: about six steps plus a running server per package, archives packed and unpacked again (double disk and time at hundreds of tiles), no incremental top-up during a build. Versions, checksums and update display matter only once packages are shared with others; it can be added later on the same `artifacts/<package>/` directory without touching OXO. The one safety property worth having now — no replacement while `run` serves — is in D5.
- **Pointing OXO straight at an XEarthLayer directory.** A package needs the merged layout (`Earth nav data/`, flat `terrain/`, `textures/`) plus `xearthlayer_scenery_package.txt`, which per-tile egress does not produce; the XEL patches directory accepts whole `zOrtho4XP_*` tiles (`xearthlayer/src/config/settings.rs:255`) but outranks every package, airports included.

## Out of scope

- Tiles **with** downloaded imagery (JPEG/DDS, self-contained). This plan covers the **mesh-only** tiles XEarthLayer streams imagery onto — the operator's stated future use of OXO. Whether imagery tiles (and future light embedding) also belong in OXO is analysed separately.

- Rebuilding existing packages with OXO (only on demand, region by region, per D6).
- `xearthlayer-publish` and any public release.
- Overlays in own packages.
- XEL runtime patches and the rest of `xearthlayer-config`.
- The texture-bytes sanity floor (deferred in the worker design); `oxo-package` validation is the gate meanwhile.

## Migration

### M0 — Checks ✅ (2026-10-23, issue #1)

DEM lookup identical in the image's Ortho4XP; patch copies identical; Sonny
1″ present for the pilot tiles `+48+010`, `+48+011`, `+48+012`.

### M1 — Standalone setup

1. Import build patches: `*.patch.osm` from the legacy tree into `ops/patches/` (layout kept), commit.
2. Import Sonny: reflink-copy every `.hgt` into `/mnt/xplane_data/oxo/dem/<block>/` (block = Ortho4XP's `round_latlon`, the 10° floor) with `ops/bin/import-dem`, rerunnable.
3. `ops/bin/oxo-package` per D5, tests first.
4. `ops/worker-pod.yaml` with real hostPaths (patches, dem ro, artifacts, empty content), `ops/specs/house-profile.example.toml`, `ops/README.md` runbook (PostgreSQL on `oxo-pg`, controld, image, pod, submit, package).

### M2 — Pilot (compare against legacy)

1. `ops/specs/oxo_pilot.toml`: `+48+010`, `+48+011`, `+48+012`, house profile, `target.root = /mnt/xplane_data/oxo/artifacts/oxo_pilot`.
2. One worker pod; job reaches `complete`. This also proves the read-only dem mount.
3. `oxo-package ops/specs/oxo_pilot.toml --code A4_PILOT` (outranks `A5_EU` per file).
4. Compare with the legacy tiles: DSF size/triangles, `.ter` names, masks, Sonny terrain visibly used; fly over in the sim.
5. Remove the pilot package. Exit: every step from `ops/README.md`, nothing read from the legacy install.

### M3 — First real package

1. Choose a region not yet built (no overlap with any own package); check its 1″/3″ DEM coverage in `oxo/dem`.
2. Tile-list helper `ops/bin/oxo-tiles` (land = has a DSF in an installed base package; no overlap with own packages — the `add-tiles` rules) emitting `tiles = [...]`.
3. Several worker pods; `oxo-package … --code A5_<REG>`.

### M4 — Steady state, legacy retired

- New own packages are built only from this repo.
- `xearthlayer-config` build skills (`add-tiles`, `build-workers`, `sync-xel-package`, `auto-sync-package`) are marked legacy; the know-how lives in `ops/README.md` (and, if it earns it, a skill in this repo).
- The legacy Ortho4XP install and `OrthoForge/Patches` can then be archived or deleted at any time without affecting OXO. Existing packages stay installed.

## Changes by repository

| Repo | Change |
|---|---|
| this fork | `ops/` (patches, specs, pod spec, `oxo-package`, `import-dem`, later `oxo-tiles`, runbook). No changes to crates, `deploy/`, `worker/`. |
| host | `/mnt/xplane_data/oxo/{dem,artifacts,content}`, Podman volume `oxo-pg`. |
| xearthlayer-config | none required; build skills marked legacy in M4. |
| legacy Ortho4XP | none; retire after M4. |

## Open decisions

- Priority code for the pilot (`A4_PILOT` proposed) and naming of the first OXO region package.
- Which region is the first real package (M3).
