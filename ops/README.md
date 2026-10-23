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
| `ops/worker-pod.yaml` | Worker pod with this host's paths. |
| `ops/bin/import-dem` | Flat `.hgt` → `Elevation_data` layout (btrfs reflinks). |
| `ops/bin/oxo-package` | Delivered tiles → `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`. |
| `ops/ledger/<package>/` | The books: one `<region_code>-r<rev>.toml` per submitted job, `installs.log`. Committed. |
| `ops/bin/oxo-whence <tile>` | How a tile was built: builds newest first, commits, DEM, patches, deviations from samsoir, installs. |
| `/mnt/xplane_data/oxo/dem/` | Sonny/viewfinder DEMs, Ortho4XP layout, mounted read-only. |
| `/mnt/xplane_data/oxo/artifacts/<package>/` | Delivered `zOrtho4XP_<tile>/` dirs (spec `target.root`). |
| `/mnt/xplane_data/oxo/content/` | Empty on purpose (no overlays). |

Tests for the scripts: `python3 -m unittest discover -s ops/tests`.

## One-time setup

```sh
# Podman (Debian 13)
pkexec /usr/bin/apt-get install -y podman

# DEMs (already done 2026-10-23; rerunnable, copies only what is missing)
ops/bin/import-dem "/mnt/xplane_data/docker/Ortho4XP/Global Elevation Data by MM" /mnt/xplane_data/oxo/dem
mkdir -p /mnt/xplane_data/oxo/artifacts /mnt/xplane_data/oxo/content

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
cargo run --release -p oxo-controld -- \
  --database-url postgres://postgres:oxo@127.0.0.1:55433/postgres --bind 0.0.0.0:8080

# 2. Package file: copy ops/packages/oxo_pilot.toml, set metadata (own
#    region_code), target.root = /mnt/xplane_data/oxo/artifacts/<name>, groups.
mkdir -p /mnt/xplane_data/oxo/artifacts/<name>
ops/bin/oxo-compose ops/packages/<name>.toml            # inspect the composed specs
ops/bin/oxo-compose ops/packages/<name>.toml --out /tmp/specs && \
  for f in /tmp/specs/*.toml; do cargo run -q -p oxo-spec-cli -- validate "$f"; done

# 3. Submit, one job per group. A job is identified by (region_code, revision):
#    resubmitting an identical spec returns the existing job; a changed spec under
#    the same pair is refused (409) — bump revision to rebuild or change anything.
#    Refuses with uncommitted changes in ops/ (the ledger must name a real commit).
git add ops/packages/<name>.toml && git commit -m "ops: package <name>"
ops/bin/oxo-compose ops/packages/<name>.toml --submit http://127.0.0.1:8080
git add ops/ledger && git commit -m "ledger: submit <name>"

# 4. Workers (more: copy ops/worker-pod.yaml with another metadata.name)
podman kube play ops/worker-pod.yaml
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>              # complete / failed / in_progress
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>/throughput
podman logs -f oxo-worker-1-worker

# 5. Package (refuses while `xearthlayer run` is serving)
ops/bin/oxo-package ops/packages/<name>.toml --code A5_<REG> --dry-run
ops/bin/oxo-package ops/packages/<name>.toml --code A5_<REG>
git add ops/ledger && git commit -m "ledger: install <name>"

# Later: how was a tile built?
ops/bin/oxo-whence +48+011

podman kube down ops/worker-pod.yaml
```

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
