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
| Packaging | `xearthlayer-config/bin/sync-xel-package` copies `done` tiles from `zOrthos_<name>/` (+ `build_status.tsv`) into `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`, validates (`--strict`), writes `xearthlayer_scenery_package.txt` (code on line 3, version 99.99.99). | Egress commits a whole `zOrtho4XP_<tile>/` atomically into `target.root` (`oxo-worker/src/exec.rs:228-268`); the tile cfg is withheld on purpose (`exec.rs` `ships()`). |
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
  ops/packages/<package>.toml                artifacts/<package>/zOrtho4XP_<tile>/
  ops/profiles/house.toml                    content/                  (empty; overlays off)
  ops/bin/oxo-package, import-dem            podman volume oxo-pg      (PostgreSQL data)
  ops/README.md (runbook)

ops/packages/<package>.toml ─oxo-compose─POST /api/v1/jobs──▶ oxo-controld ── PostgreSQL (oxo-pg)
                                                    ▲ claim/report
worker pods (oxo-worker image, stock Shred86 Ortho4XP)
  patches-active ← <repo>/ops/patches (ro)   dem ← oxo/dem (ro)   artifacts ← oxo/artifacts
      │
      ▼
oxo/artifacts/<package>/zOrtho4XP_<tile>/
      │  ops/bin/oxo-package ops/packages/<package>.toml --code A5_<REG>
      ▼
~/.local/share/xearthlayer/packages/zzXEL_<package>_ortho/
```

The `ops/` directory is fork-only operator material; upstream code paths
(`deploy/`, `worker/`, crates) stay untouched so upstream merges remain clean.

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | **Stock Shred86 Ortho4XP, no fork.** The image's pinned commit stays. | The legacy fork's only source change is Overpass server weighting; stock `random` is kept, over a fork-local `overpass_servers.txt` that lists only DE (revised 2026-10-23: KU timed out on every request; FR serves three-month-old data, and with two entries `random` alternates servers on *every* query, so one layer mixed two snapshots and Ortho4XP failed on a deleted node). `apt_compat_patch` only matters for OrthoForge `.apt` pickles in a shared OSM cache, which pods don't have. `dem_lock_patch` guards concurrent DEM downloads, which D3 rules out. |
| D2 | **Build patches live in this repo** under `ops/patches/`, in Ortho4XP's block-nested layout, mounted read-only. Imported once from the legacy tree (`*.patch.osm` only, ≈ 30 MB); from then on edited and versioned here. | Standalone, with history. The 223 MB `.raw` is not a patch file and stays behind. |
| D3 | **Sonny DEMs in an OXO-owned directory in native layout.** `/mnt/xplane_data/oxo/dem/<block>/N..E...hgt` as real files, created once by a reflink copy (`cp --reflink=always`, btrfs: no extra space, independent of the legacy files). Mounted read-only as the pod's dem-cache. Stock `View` source, no `custom_dem`, no symlink tricks, no extra volume. | Deleting the legacy install later cannot break OXO. Read-only means a tile without coverage fails loudly instead of silently building on downloaded data, and no concurrent writes means no download race. |
| D4 | **Settings in three layers, samsoir first** (revised 2026-10-23): baseline = upstream `docs/examples/example-region.toml` (samsoir's production tuning, read in place so his changes arrive with each merge); `ops/profiles/house.toml` holds only deliberate deviations (BI, `include_overlays = false`, `cover_extent` 1 km); `ops/packages/<name>.toml` holds metadata, target and tile groups with per-group overrides (e.g. `masking_mode`). `ops/bin/oxo-compose` merges them into one spec per group (OXO takes one parameter set per spec); groups share `name` and `target.root`, region codes get a group suffix. ZL16 everywhere, airports ZL18 — the legacy house values (ZL17, rocks, …) are not carried over. | Streaming performance: samsoir's settings are tuned for XEL. Deviations stay few, visible and reasoned; upstream tuning changes flow in without copying. |
| D5 | **Packaging script in this repo: `ops/bin/oxo-package`** (Python, with tests). Reads the spec (name, `target.root`), refuses while `xearthlayer run` serves (PID in `~/.local/state/xearthlayer/xearthlayer.lock` alive — the same check XEL's installer makes), validates every tile with the legacy `--strict` rules minus the cfg check, since egress withholds the cfg (DSF ≥ 10 KB, `.ter` → `_BI<zl>.dds`, which also enforces BI, mask PNG, no partials), and checks `--code` against `^[A-Za-z0-9][A-Za-z0-9_-]*$` before anything else, copies DSF / `.ter` / mask PNGs (all top-level, as the legacy sync does) into `zzXEL_<package>_ortho/`, writes `xearthlayer_scenery_package.txt` with the given code. Every `zOrtho4XP_*` present counts as done (egress is atomic). | Standalone; the rules are ported, not reinvented. `sync-xel-package` stays in `xearthlayer-config` for the frozen legacy builds only, so the two never need to agree. |
| D6 | **Old packages stay byte-for-byte as they are** (revised 2026-10-23, see D8): nothing is written into an existing `zzXEL_*` directory; rebuilt tiles shadow old ones from the OXO package instead. | Per-file priority makes accidental shadowing the main risk; an untouched legacy package is its own rollback. |
| D7 | **Operations without new Rust code:** Podman installed on the host (Debian package); PostgreSQL as a Podman container on the named volume `oxo-pg`; `oxo-controld --bind 0.0.0.0:8080`; worker `OXO_CONTROL_URL = http://host.containers.internal:8080`; artifacts mounted at the same path as on the host so `target.root` is valid for worker and `oxo-package`; one `region_code` per package (jobs are keyed by `region_code` + `revision`; a resubmit returns the existing job if planned tasks, `max_attempts`/`backoff_seconds` and the worker payload (`oxo-control/src/planner.rs` `WorkerPayload`) match, else 409; `metadata.name` and alert destinations are not compared); `OXO_MIN_FREE_SCRATCH_BYTES` at its 8 GiB ZL16 default; no `overpass_server_choice` override (D1). Jobs submitted with `curl`; the console (sub-project 5) is not a prerequisite. All of it written down in `ops/README.md` and `ops/worker-pod.yaml` (real paths, no `EDIT ME`). | Everything needed exists; `make pg-up` is disposable. |
| D8 | **Adopt, don't switch tools** (2026-10-23). The operator's 10 own packages (version `99.99.99`, codes `A0_*`/`A5_*`; the 17 `0.5.0` packages are samsoir's and are not adopted) are recorded once as an as-is baseline in `ops/adopted/<package>.toml`. Every value carries its origin: *observed* from the installed files (provider and ZL per tile from the DSF-referenced `.ter` names, mask ZL from the PNG names, `sim/creation_agent`), *cfg* from a legacy `Ortho4XP_<tile>.cfg` only where it agrees with the observed ZLs, else *unknown*. Any later work on such a tile happens in OXO, and rebuilt tiles go into **two** packages that mirror the legacy apt/sonny split (revised 2026-10-23): tiles with build patches (airports whose scenery needs them) into `zzXEL_oxo_apt_ortho`, code `A00_OXO`, which XEL sorts before every `A0_*` (lower-cased byte order, `0` < `_`; `xearthlayer/src/ortho_union/source.rs:164`, `builder.rs:302`), so a rebuilt airport tile wins over its legacy copy; every other rebuilt tile into `zzXEL_oxo_sonny_ortho`, code `A4_OXO` — after the legacy `A0_*` airports, so an unpatched rebuild can never shadow a patched airport tile, and before the legacy `A5_*` Sonny packages and samsoir's regions. A tile belongs to `oxo_apt` exactly when it has patch files in `ops/patches/`. On rebuild, `oxo-compose` shows each *known* legacy value that differs from samsoir + house and asks once: keep or default; the answer is persisted as a group override with a reason in the package file. Unknown values follow samsoir without asking, and the ledger says so. | Legacy config is mostly unrecoverable (inventory 2026-10-23: `eu_sonny` 167 of 2036 tiles have a cfg by name, and the one checked, `+48+012`, describes an older 36 MB ZL17 build, not the installed 63 MB ZL16/17/18 one), so only observed facts are trustworthy. Two extra packages, not one per region: XEL probes `terrain/`/`textures/` lazily across all packages in priority order (`ortho_union/index.rs:297`), so every package adds a lookup. Two rather than one because the tiers matter differently: the patched airports are what the operator's scenery depends on, the Sonny tiles are nice to have (samsoir's packages cover the same ground with a coarser mesh, which hardly shows at cruise altitude), and only a separate lower tier keeps an unpatched rebuild from outranking a patched airport. |

## Rejected alternatives

- **Mounting the legacy patch tree and DEM directory in place** (first version of this plan). Rejected: keeps OXO tied to an installation that is meant to be retired; the relative DEM symlinks also needed an extra mount to resolve.
- **Packaging through XEarthLayer's own package path** (`xearthlayer-publish add → build → urls → version --bump → release`, a local HTTP server for the library — XEL fetches libraries over HTTP only, `xearthlayer/src/manager/cache.rs` — an extra `library_url`, then `xearthlayer packages install`). Custom codes such as `A5_EU` would be accepted. Rejected for now: about six steps plus a running server per package, archives packed and unpacked again (double disk and time at hundreds of tiles), no incremental top-up during a build. Versions, checksums and update display matter only once packages are shared with others; it can be added later on the same `artifacts/<package>/` directory without touching OXO. The one safety property worth having now — no replacement while `run` serves — is in D5.
- **Pointing OXO straight at an XEarthLayer directory.** A package needs the merged layout (`Earth nav data/`, flat `terrain/`, `textures/`) plus `xearthlayer_scenery_package.txt`, which per-tile egress does not produce; the XEL patches directory accepts whole `zOrtho4XP_*` tiles (`xearthlayer/src/config/settings.rs:255`) but outranks every package, airports included.

## Out of scope

- Tiles **with** downloaded imagery (JPEG/DDS, self-contained). OXO is the tool for the operator's **mesh-only** tiles that XEarthLayer streams imagery onto. Imagery tiles stay with an existing tool (legacy Ortho4XP / OrthoForge / orthostudio-xp), analysed 2026-10-23: OXO's egress drops `jpg`/`jpeg`/`dds` by design (`oxo-worker/src/exec.rs:134`), an imagery artifact would be ~2.6 GB at ZL16 instead of ~64 MB, and nothing throttles the imagery provider across pods. Night lighting is no argument for OXO there: it is generated by XEL at run time from a recipe (below), so a self-contained tile cannot use it. XPME needs only DSF + masks, which mesh-only output already provides.

## Follow-up: night lighting from upstream

XEarthLayer's night-lighting design (`xearthlayer/docs/dev/night-lighting-design.md`, branch `develop/0.5.0`) states that OXO writes a `TEXTURE_LIT … _LIT.dds` / `LUMINANCE 150` line into every land `.ter` and one recipe `<tile>.oxn` per tile; XEL renders the lit texture at run time from the user's own X-Plane art. That OXO side is not on upstream `main` yet (9a1684c). When it lands it reaches this fork through `main` → `ops`; then `oxo-package` must carry the `.oxn` recipes into the package's `night/` directory, and night packages need XEL ≥ 0.5.0. Tracked as its own issue.

- Bulk rebuilds of adopted packages; tiles are rebuilt on demand (D8). Rewriting or deleting legacy package directories.
- `xearthlayer-publish` and any public release.
- Overlays in own packages.
- XEL runtime patches and the rest of `xearthlayer-config`.
- The texture-bytes sanity floor (deferred in the worker design); `oxo-package` validation is the gate meanwhile.

## Follow-up: OSM data without waiting on Overpass

Measured in the pilot (2026-10-23): ~19 of the first tile's 24 min were Overpass downloads; KU timed out on every request (60 s each). Ortho4XP reuses `OSM_data/<block>/<tile>/<tile>_<layer>.osm.bz2` when the file exists (`O4_OSM_Utils.py:427-429`), but in the pod `OSM_data` is a symlink onto scratch, so every task downloads everything again. Three steps:

1. **Done:** `ops/o4-overlay/overpass_servers.txt` (DE, FR; KU dropped) via `OXO_O4_CONFIG_OVERLAY`.
2. **Persistent OSM cache** (decision pending, own issue): an `osm-cache` volume beside `dem-cache`, seeded once by reflink from the legacy `OSM_data` (7.9 GB, 4227 tiles, Aug 2026); the runner copies a tile's layers into scratch before the build and publishes new ones atomically afterwards. Not a plain mount over `scratch/OSM_data`: worker cleanup `remove_dir_all`s it (`oxo-worker/src/exec.rs:273`). Touches `worker/` — upstream PR or fork-only is open.
3. **`ops/bin/osm-bake`** (idea from OrthoForge `tools/osm_prebake/bake.py`, GPL v3 — reimplemented, not copied): Geofabrik `.pbf` → `osmium tags-filter` prefilter → per tile `osmium extract -s complete_ways` → per layer `osmium tags-filter` with the same selectors Ortho4XP queries (`small_roads` at the widest road level; `update_dicosm` re-filters on load) → `.osm.bz2` written via `.part` + rename; empty layers written as an empty `<osm/>`, never skipped; only tiles wholly inside the extract's `.poly`, as orthostudio does. Output is the cache of step 2.

## Migration

### M0 — Checks ✅ (2026-10-23, issue #1)

DEM lookup identical in the image's Ortho4XP; patch copies identical; Sonny
1″ present for the pilot tiles `+48+010`, `+48+011`, `+48+012`.

### M1 — Standalone setup

1. Import build patches: `*.patch.osm` from the legacy tree into `ops/patches/` (layout kept), commit.
2. Import Sonny: reflink-copy every `.hgt` into `/mnt/xplane_data/oxo/dem/<block>/` (block = Ortho4XP's `round_latlon`, the 10° floor) with `ops/bin/import-dem`, rerunnable.
3. `ops/bin/oxo-package` per D5, tests first.
4. `ops/worker-pod.yaml` with real hostPaths (patches, dem ro, artifacts, empty content), `ops/profiles/house.toml` + `ops/bin/oxo-compose` (D4), `ops/README.md` runbook (PostgreSQL on `oxo-pg`, controld, image, pod, submit, package).

### M1b — Provenance ledger (issue #7)

Plain files in git, not a database (small volume; git gives history and ties each record to its commit; a SQLite index could be derived later). `oxo-compose --submit` refuses with uncommitted changes in `ops/` and writes `ops/ledger/<package>/<region_code>-r<rev>.toml` (exact spec, job id, `ops` and Ortho4XP commits, patches tree, origin layer of every deviation from samsoir, DEM and patches per tile); `oxo-package` appends `installs.log`; `ops/bin/oxo-whence <tile>` answers how a tile was built.

### M2 — Pilot (compare against legacy)

1. `ops/packages/oxo_pilot.toml`: `+48+010`, `+48+011`, `+48+012`, samsoir baseline + house, `target.root = /mnt/xplane_data/oxo/artifacts/oxo_pilot`.
2. One worker pod; job reaches `complete`. This also proves the read-only dem mount.
3. `oxo-package ops/packages/oxo_pilot.toml --code A4_PILOT` (outranks `A5_EU` per file).
4. Compare with the legacy tiles: DSF size/triangles, `.ter` names, masks, Sonny terrain visibly used; fly over in the sim.
5. Remove the pilot package. Exit: every step from `ops/README.md`, nothing read from the legacy install, `oxo-whence +48+011` answers completely.

### M2b — Adopt existing own packages (D8)

1. `ops/bin/oxo-adopt <zzXEL dir>` (tests first): one `ops/adopted/<package>.toml` per own package, values with origin observed / cfg / unknown; cfg sources `/mnt/xplane_data/Orthos/Ortho4XP/src/**/zOrtho4XP_<tile>/` and OrthoStudio `tile_settings.cfg` + `orthostudio.toml`, values normalised and embedded (the legacy trees stay disposable).
2. Adopt the 10 own packages, commit.
3. `oxo-whence` shows the adoption entry as the oldest state of a tile.

### M2c — Rebuild single tiles into `zzXEL_oxo_apt_ortho` / `zzXEL_oxo_sonny_ortho` (D8)

1. `ops/packages/oxo_apt.toml` (`name = "oxo_apt"`, tiles with patches only) and `ops/packages/oxo_sonny.toml` (`name = "oxo_sonny"`), one group per rebuild batch each; `oxo-compose --group ID` submits only that batch.
2. Keep-or-default step in `oxo-compose`: per known differing legacy value ask once, persist as group override with reason; `--submit` refuses while undecided.
3. `oxo-package ops/packages/oxo_apt.toml --code A00_OXO` and `… oxo_sonny.toml --code A4_OXO` stage the package fresh from `target.root` and swap it in, so no stale files survive a rebuild.
4. First run: the M2 pilot tiles, after the comparison — `+48+011` (EDDM patch) into `oxo_apt`, `+48+010` and `+48+012` into `oxo_sonny`.
5. Focus is `oxo_apt`: the legacy `A0_*` airport tiles (53 in `eu_apt` alone). `oxo_sonny` grows only where a rebuild is wanted.

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
| host | `/mnt/xplane_data/oxo/{dem,artifacts}`, X-Plane 12 Global Scenery mounted read-only as the pod's `content` (every ortho DSF takes DEM and bathymetry rasters from it), Podman volume `oxo-pg`. |
| xearthlayer-config | none required; build skills marked legacy in M4. |
| legacy Ortho4XP | none; retire after M4. |

## Open decisions

- Whether new regions (M3) go into `zzXEL_oxo_sonny_ortho` (`A4_OXO`) instead of their own `A5_<REG>` package — fewer packages, see D8. Low priority: outside the airports, samsoir's packages suffice.
- Rebuilt tiles at ZL16 next to legacy ZL17 neighbours: seams at tile borders accepted?
- Which region is the first real package (M3).
