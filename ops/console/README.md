# ops/console — read-only operator console

A small web page for this fork that shows what OXO is doing right now: the job
queue, the worker, delivered and packaged tiles, and where they lie on a map.
It changes nothing anywhere.

`server.py` (python3 stdlib) builds one state document per request from:
PostgreSQL, read-only through `podman exec oxo-pg psql` (the OXO API has no job
list); `podman ps`/`podman logs` for the worker containers; the ledger under
`ops/ledger/`; and the installed `zzXEL_*` packages. Upstream's planned
`oxo-console` (phase 5a) is a separate thing; this is not it.

## Start

```sh
python3 ops/console/server.py            # then open http://127.0.0.1:8090/
python3 ops/console/server.py --bind 0.0.0.0   # reachable from the LAN, unauthenticated: trusted networks only
```

The page polls `GET /api/state` every 3 s (every 10 s while it fails) and
updates in place. If the server or the database is unreachable, the status bar
says so in one sentence and the last picture stays visible, greyed out.

## What it shows

- **Status bar** (sticky): DB dot, summary, the most urgent problem as one
  sentence (stale heartbeat, stopped container, abandoned tiles; tiles
  "cancelled by operator" do not count as a problem), time since the last update.
- **Band**: QUEUE | WORKER lanes (Ortho4XP step bar S1 ▸ S2 ▸ S2.5 ▸ S3, a ring
  that fills over 30 min of one step, last log line) | DELIVERED | PACKAGED (by
  package priority, plus a list of all installed packages). Rejected tiles
  go to the AUSSCHUSS gutter (abandoned). One chip per task. Only the newest task per
  package and tile is shown (plus any older one still pending or claimed, since a
  worker will build it); older revisions, tasks cancelled by the operator and tasks
  whose package was installed and later removed stay in the job strip only, dimmed.
  When a task changes state, its chip glides to the new column.
- **Job strip**: one row per job with a state bar.
- **Map** (Leaflet 1.9.4, OpenStreetMap tiles, dimmed in dark mode): every tile as a 1°×1° rectangle in
  the same palette (pending, claimed, succeeded, packaged, abandoned). A claimed
  tile glows, and a tile pings once when it is claimed or delivered. The
  worker's label sits on its tile. If the basemap is unavailable, a lat/lon
  grid is drawn instead. Without Leaflet (offline) the map becomes a compact
  tile grid.
- **Ortho4XP errors**: lines starting with `ERROR` in a task's log span are flagged
  on its chip, in the map tooltip and (when nothing more urgent exists) in the
  status bar. They come from `podman logs` (journald), so they survive a
  container restart but not a pod re-creation, and only while the task still lies
  within the last 20000 log lines the console reads (`LOG_LINES`), so an old error
  can drop out of view after a few dozen later tasks on the same worker; the durable guard is the
  pre-build OSM check (`oxo-compose --osm-check`).
- **Shared selection**: hover or click a chip, a map tile or a job, and the
  same tiles light up everywhere. A job click fits the map to that job. Esc
  clears the selection.

On phones (≤ 700 px) a "Band | Karte" switch replaces the stacked layout. The
browser remembers the chosen tab. `prefers-reduced-motion` turns off the glide,
the ping and the glow.

Files: `static/index.html`, `static/style.css`, `static/app.js` (ES module, no
build step). `mockups/` holds the three design studies the page was built from
(design reference only, simulated data).

## Tests

```sh
cd ops/console && python3 -m unittest discover -s tests
```

`tests/sample_state.json` is the `/api/state` contract (a busy worker and a
failed job). To view the frontend against it, serve a copy of `static/` with
that file at `api/state` via `python3 -m http.server`.
