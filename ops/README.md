# ops — own XEarthLayer packages on this host

Fork-only operator material (branch `ops`). Everything needed to go from a
region spec to an installed XEarthLayer package lives here or under
`/mnt/xplane_data/oxo/`; nothing reads the legacy Ortho4XP install.
Why it looks like this: `docs/plans/2026-10-23-own-package-production.md`.

| Path | What |
|---|---|
| `ops/patches/<block>/<tile>/*.patch.osm` | Ortho4XP build patches, mounted read-only into every worker. Edit and commit here. |
| `ops/specs/<package>.toml` | One region spec per package; start from `house-profile.example.toml`. |
| `ops/worker-pod.yaml` | Worker pod with this host's paths. |
| `ops/bin/import-dem` | Flat `.hgt` → `Elevation_data` layout (btrfs reflinks). |
| `ops/bin/oxo-package` | Delivered tiles → `~/.local/share/xearthlayer/packages/zzXEL_<name>_ortho/`. |
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

# 2. Spec: copy the house profile, set tiles, metadata.name, a region_code of
#    its own, target.root = /mnt/xplane_data/oxo/artifacts/<name>.
cp ops/specs/house-profile.example.toml ops/specs/<name>.toml
cargo run -q -p oxo-spec-cli -- validate ops/specs/<name>.toml
mkdir -p /mnt/xplane_data/oxo/artifacts/<name>

# 3. Submit. A job is identified by (region_code, revision): resubmitting the
#    same pair returns the existing job — bump revision to rebuild.
curl -sS -X POST --data-binary @ops/specs/<name>.toml http://127.0.0.1:8080/api/v1/jobs

# 4. Workers (more: copy ops/worker-pod.yaml with another metadata.name)
podman kube play ops/worker-pod.yaml
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>              # complete / failed / in_progress
curl -sS http://127.0.0.1:8080/api/v1/jobs/<job_id>/throughput
podman logs -f oxo-worker-1-worker

# 5. Package (refuses while `xearthlayer run` is serving)
ops/bin/oxo-package ops/specs/<name>.toml --code A5_<REG> --dry-run
ops/bin/oxo-package ops/specs/<name>.toml --code A5_<REG>

podman kube down ops/worker-pod.yaml
```

## Priority codes

XEarthLayer resolves per file, lowest code (byte order) wins; patches beat
every package. Own ortho packages sit at `A5_<REG>`, airports at `A0_*`,
base regions below. A code that sorts before an existing package's overrides
it wherever both have the same file — choose deliberately. Existing legacy
packages (`zzXEL_*`) stay as they are.
