#!/usr/bin/env python3
"""Read-only OXO operator console: serves static/ and GET /api/state.

Usage: python3 ops/console/server.py [--bind 127.0.0.1] [--port 8090]
Never writes anything; every external command goes through run(argv).
"""

import argparse
import csv
import datetime as dt
import functools
import http.server
import io
import json
import pathlib
import re
import subprocess
import threading
import time
import tomllib

HERE = pathlib.Path(__file__).resolve().parent
LEDGER_DIR = HERE.parent / "ledger"
PACKAGES_DIR = pathlib.Path.home() / ".local/share/xearthlayer/packages"
STATIC_DIR = HERE / "static"
STATE_TTL, PACKAGES_TTL = 2.0, 60.0
STATES = ("pending", "claimed", "succeeded", "abandoned")

PSQL = ["podman", "exec", "oxo-pg", "psql", "-U", "postgres", "-At", "--csv", "-c"]
JOBS_WHERE = "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 50"


def ts(col):
    return f"to_char({col} AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"


JOBS_SQL = (f"SELECT id, region_code, revision, max_attempts, {ts('created_at')} "
            "FROM jobs ORDER BY created_at DESC LIMIT 50")
TASKS_SQL = (f"SELECT id, job_id, tile, task_type, state, attempts, claimed_by, "
             f"{ts('claimed_at')}, {ts('last_heartbeat_at')}, last_failure "
             f"FROM tasks WHERE job_id IN ({JOBS_WHERE}) ORDER BY tile")

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CLAIMED = re.compile(r"oxo_worker::run: claimed task (\S+) (\S+) (\S+) attempt (\d+)")
FINISHED = re.compile(r"oxo_worker::run: (?:completed|failed) task ([^\s:]+)")


def run(argv, merge=False):
    """Run argv, return stdout (plus stderr if merge); raise RuntimeError on failure."""
    try:
        p = subprocess.run(argv, capture_output=not merge, text=True, timeout=20,
                           stdout=subprocess.PIPE if merge else None,
                           stderr=subprocess.STDOUT if merge else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(str(e)) from e
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "").strip().splitlines()
        raise RuntimeError(msg[0] if msg else f"exit {p.returncode}")
    return p.stdout


def iso_utc(stamp):
    """RFC3339 with any fraction and offset -> 'YYYY-MM-DDTHH:MM:SSZ'."""
    stamp = re.sub(r"\.\d+", "", stamp).replace("Z", "+00:00")
    return dt.datetime.fromisoformat(stamp).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_unix(secs):
    return dt.datetime.fromtimestamp(secs, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def job_state(counts):
    if counts["pending"] or counts["claimed"]:
        return "in_progress"
    return "failed" if counts["abandoned"] else "complete"


def rows(text):
    return [[c if c != "" else None for c in r] for r in csv.reader(io.StringIO(text)) if r]


class Console:
    def __init__(self, run=run, ledger_dir=LEDGER_DIR, packages_dir=PACKAGES_DIR, clock=time.time):
        self.run, self.ledger_dir, self.packages_dir, self.clock = run, ledger_dir, packages_dir, clock
        self.lock = threading.Lock()
        self.cached = self.cached_at = self.pkgs = self.pkgs_at = None

    def state(self):
        with self.lock:
            now = self.clock()
            if self.cached is None or now - self.cached_at >= STATE_TTL:
                if self.pkgs is None or now - self.pkgs_at >= PACKAGES_TTL:
                    self.pkgs, self.pkgs_at = self.packages(), now
                database, jobs = self.jobs()
                self.cached, self.cached_at = {
                    "generated_at": iso_unix(now),
                    "database": database,
                    "jobs": jobs,
                    "workers": self.workers(),
                    "packages": self.pkgs,
                    "installs": self.installs(),
                }, now
            return self.cached

    def ledger(self):
        """job_id -> parsed ledger record."""
        records = {}
        for f in sorted(self.ledger_dir.glob("*/*-r*.toml")):
            rec = tomllib.loads(f.read_text())
            records[rec.get("provenance", {}).get("job_id")] = rec
        return records

    def jobs(self):
        try:
            job_rows = rows(self.run(PSQL + [JOBS_SQL]))
            task_rows = rows(self.run(PSQL + [TASKS_SQL]))
        except RuntimeError as e:
            return {"reachable": False, "error": str(e)[:200]}, []
        ledger = self.ledger()
        jobs, by_id = [], {}
        for jid, region, rev, max_att, created in job_rows:
            rec = ledger.get(jid, {})
            job = {"id": jid, "region_code": region, "revision": int(rev),
                   "package": rec.get("spec", {}).get("metadata", {}).get("name"),
                   "created_at": created, "max_attempts": int(max_att),
                   "state": None, "counts": dict.fromkeys(STATES, 0), "total": 0, "tasks": [],
                   "_tiles": rec.get("tiles", {})}
            jobs.append(job)
            by_id[jid] = job
        for tid, jid, tile, ttype, st, att, by, cat, hb, fail in task_rows:
            job = by_id.get(jid)
            if job is None:
                continue
            lt = job["_tiles"].get(tile, {})
            job["tasks"].append({"id": tid, "tile": tile, "task_type": ttype, "state": st,
                                 "attempts": int(att), "claimed_by": by, "claimed_at": cat,
                                 "last_heartbeat_at": hb, "last_failure": fail,
                                 "replaces": lt.get("replaces"), "patches": lt.get("patches", [])})
            job["counts"][st] = job["counts"].get(st, 0) + 1
            job["total"] += 1
        for job in jobs:
            del job["_tiles"]
            job["state"] = job_state(job["counts"])
        return {"reachable": True, "error": None}, jobs

    def installs(self):
        out = []
        for f in self.ledger_dir.glob("*/installs.log"):
            for line in f.read_text().splitlines():
                parts = line.split("\t")
                if len(parts) == 4:
                    out.append({"at": parts[0], "code": parts[1], "package": parts[2],
                                "tiles": [t for t in parts[3].split(",") if t]})
        out.sort(key=lambda i: i["at"], reverse=True)
        return out[:20]

    def workers(self):
        try:
            containers = json.loads(self.run(["podman", "ps", "-a", "--format", "json"]))
        except (RuntimeError, ValueError):
            return []
        out = []
        for c in containers:
            name = c["Names"][0]
            if "oxo-worker" not in name or name.endswith("-infra"):
                continue
            w = {"name": name, "state": c.get("State"),
                 "started_at": iso_unix(c["StartedAt"]) if c.get("StartedAt") else None,
                 "current": None, "log_tail": []}
            try:
                logs = self.run(["podman", "logs", "--timestamps", "--tail", "400", name], merge=True)
            except RuntimeError:
                logs = ""
            w["current"], w["log_tail"] = parse_logs(logs)
            out.append(w)
        return out

    def packages(self):
        out = []
        for f in sorted(self.packages_dir.glob("*/xearthlayer_scenery_package.txt")):
            lines = f.read_text().splitlines()
            fields = lines[2].split() if len(lines) > 2 else []
            if len(fields) < 2:
                continue
            name, (code, version) = f.parent.name, fields[:2]
            owner = "oxo" if name.startswith("zzXEL_oxo_") else "own" if version == "99.99.99" else "samsoir"
            out.append({"name": name, "code": code, "version": version,
                        "tiles": len(list(f.parent.glob("Earth nav data/*/*.dsf"))), "owner": owner})
        out.sort(key=lambda p: p["code"].lower())
        return out


def parse_logs(text):
    """-> (current task or None, last 40 non-empty lines as {at, line})."""
    entries = []
    for raw in text.splitlines():
        stamp, _, line = ANSI.sub("", raw).partition(" ")
        try:
            at = iso_utc(stamp)
        except ValueError:
            continue
        entries.append((at, line.rstrip()))
    current = None
    for at, line in entries:
        if m := CLAIMED.search(line):
            current = {"task_id": m[1], "task_type": m[2], "tile": m[3], "attempt": int(m[4]),
                       "since": at, "step": None, "step_since": None}
        elif (m := FINISHED.search(line)) and current and m[1] == current["task_id"]:
            current = None
        elif current and line.startswith("Step "):
            current["step"], current["step_since"] = line.rstrip(" :"), at
    if current:
        current = {k: current[k] for k in ("task_id", "tile", "task_type", "attempt",
                                           "since", "step", "step_since")}
    tail = [{"at": at, "line": line} for at, line in entries if line.strip()][-40:]
    return current, tail


PLACEHOLDER = (b"<!doctype html><title>OXO console</title>"
               b"<p>Frontend not built yet. State: <a href='/api/state'>/api/state</a></p>")


def make_server(bind, port, console, static_dir=STATIC_DIR):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                return self.send(json.dumps(console.state()).encode(), "application/json")
            if path in ("/", "/index.html") and not (static_dir / "index.html").exists():
                return self.send(PLACEHOLDER, "text/html; charset=utf-8")
            return super().do_GET()

        def send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    handler = functools.partial(Handler, directory=str(static_dir))
    return http.server.ThreadingHTTPServer((bind, port), handler)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    srv = make_server(args.bind, args.port, Console())
    print(f"OXO console on http://{args.bind}:{args.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
