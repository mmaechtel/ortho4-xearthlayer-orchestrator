"""Unit tests for ops/console/server.py — no podman, no postgres."""

import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server  # noqa: E402

SAMPLE = json.loads((pathlib.Path(__file__).parent / "sample_state.json").read_text())

JOB_APT = "5cadb9e9-d37e-4016-af57-165443649137"
JOB_SONNY = "74ac7077-0eb5-4283-b0ba-bb93410b3be2"
JOB_PILOT = "d125946d-ef3d-4f34-b4ce-17bc0b1dea73"
TASK_APT = "99335416-c161-437d-9007-cb1a2aecfb8d"

JOBS_CSV = (
    f"{JOB_APT},OXO-APT,1,3,2026-10-23T11:08:41Z\n"
    f"{JOB_SONNY},OXO-SONNY,1,3,2026-10-23T11:08:43Z\n"
    f"{JOB_PILOT},EU-PILOT,3,3,2026-10-23T09:10:38Z\n"
)
TASKS_CSV = (
    f"{TASK_APT},{JOB_APT},+48+011,ortho,claimed,2,oxo-worker-1,"
    "2026-10-23T11:10:12Z,2026-10-23T11:20:42Z,"
    '"prepare: target root, ""quoted""\nsecond line"\n'
    f"t-s1,{JOB_SONNY},+48+010,ortho,abandoned,1,,,,cancelled by operator\n"
    f"t-p1,{JOB_PILOT},+48+010,ortho,succeeded,1,,,,\n"
    f"t-p2,{JOB_PILOT},+48+011,ortho,succeeded,1,,,,\n"
    f"t-s2,{JOB_SONNY},+48+012,ortho,abandoned,1,,,,cancelled by operator\n"
)

PS_JSON = json.dumps([
    {"Names": ["oxo-pg"], "State": "running", "StartedAt": 1792738578},
    {"Names": ["ab1a1f782b1e-infra"], "State": "running", "StartedAt": 1792743263},
    {"Names": ["oxo-worker-1-infra"], "State": "running", "StartedAt": 1792743263},
    {"Names": ["oxo-worker-1-worker"], "State": "running", "StartedAt": 1792743263},
])

E = "\x1b"
LOGS = (
    f"2026-10-23T13:09:34.266968000+02:00 {E}[2m2026-10-23T11:09:34Z{E}[0m {E}[32m INFO{E}[0m "
    f"{E}[2moxo_worker::run{E}[0m{E}[2m:{E}[0m claimed task {TASK_APT} ortho +48+011 attempt 1\n"
    f"2026-10-23T13:09:34.270988000+02:00 INFO oxo_worker::run: failed task {TASK_APT}: prepare: boom\n"
    "2026-10-23T13:09:35.000000000+02:00 INFO oxo_worker::run: claimed task t-p1 ortho +48+010 attempt 1\n"
    "2026-10-23T13:09:36.000000000+02:00 Step 1 : Building vector data for tile +48+010 : \n"
    "2026-10-23T13:09:37.000000000+02:00 INFO oxo_worker::run: completed task t-p1\n"
    f"2026-10-23T13:10:12.285627000+02:00 INFO oxo_worker::run: claimed task {TASK_APT} ortho +48+011 attempt 2\n"
    "2026-10-23T13:10:13.605678000+02:00 Step 1 : Building vector data for tile +48+011 : \n"
    "2026-10-23T13:12:00.000000000+02:00 \n"
    "2026-10-23T13:15:00.100000000+02:00 Step 2.5 : Building masks for tile +48+011 : \n"
    "2026-10-23T13:20:35.900000000+02:00    Number of edges at this point: 124650\n"
)


def fake_run(calls=None, db_fail=False, logs=LOGS, ps=PS_JSON):
    def run(argv, merge=False):
        if calls is not None:
            calls.append((list(argv), merge))
        if "psql" in argv:
            if db_fail:
                raise RuntimeError("Error: no container with name or ID \"oxo-pg\" found")
            sql = argv[-1]
            return TASKS_CSV if "FROM tasks" in sql else JOBS_CSV
        if argv[:2] == ["podman", "ps"]:
            return ps
        if argv[:2] == ["podman", "logs"]:
            n = int(argv[argv.index("--tail") + 1]) if "--tail" in argv else None
            return "".join(logs.splitlines(keepends=True)[-n:]) if n else logs
        raise AssertionError(f"unexpected command {argv}")
    return run


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.ledger = root / "ledger"
        self.packages = root / "packages"
        write(self.ledger / "oxo_apt" / "OXO-APT-r1.toml", f'''
[provenance]
job_id = "{JOB_APT}"
[tiles."+48+011"]
dem = "1s"
patches = ["EDDM.patch.osm"]
replaces = "eu_apt (A0_EU) cfg agrees"
[spec.metadata]
name = "oxo_apt"
region_code = "OXO-APT"
revision = 1
''')
        write(self.ledger / "oxo_pilot" / "EU-PILOT-r3.toml", f'''
[provenance]
job_id = "{JOB_PILOT}"
[tiles."+48+010"]
dem = "1s"
[tiles."+48+011"]
patches = ["EDDM.patch.osm"]
[spec.metadata]
name = "oxo_pilot"
''')
        write(self.ledger / "oxo_pilot" / "installs.log",
              "2026-10-23T09:00:00Z\tA4_PILOT\tzzXEL_oxo_pilot_ortho\t+48+010\n"
              "2026-10-23T10:26:45Z\tA4_PILOT\tzzXEL_oxo_pilot_ortho\t+48+010,+48+011,+48+012\n")
        write(self.ledger / "oxo_apt" / "installs.log",
              "2026-10-23T10:00:00Z\tA00_OXO\tzzXEL_oxo_apt_ortho\t+48+011\n")
        self.pkg("zzXEL_eu-west_ortho", "EU-WEST  0.5.0", 2)
        self.pkg("zzXEL_oxo_pilot_ortho", "A4_PILOT  99.99.99", 3)
        self.pkg("zzXEL_eu_apt_ortho", "A0_EU  99.99.99", 1)

    def tearDown(self):
        self.tmp.cleanup()

    def pkg(self, name, line3, dsfs):
        d = self.packages / name
        write(d / "xearthlayer_scenery_package.txt",
              f"REGIONAL SCENERY PACKAGE\n1.0.0\n{line3}\n2026-01-01T00:00:00Z\n")
        for i in range(dsfs):
            write(d / "Earth nav data" / "+40+010" / f"+4{i}+011.dsf", "")
        write(d / "Earth nav data" / "+40+010" / "not-a-tile.txt", "")

    def console(self, run=None, clock=None):
        return server.Console(run=run or fake_run(), ledger_dir=self.ledger,
                              packages_dir=self.packages,
                              clock=clock or (lambda: 1792754460.0))


class StateShape(Fixture):
    def test_top_level_and_nested_keys_match_sample(self):
        state = self.console().state()
        self.assertEqual(set(state), set(SAMPLE))
        self.assertEqual(set(state["database"]), set(SAMPLE["database"]))
        self.assertEqual(set(state["jobs"][0]), set(SAMPLE["jobs"][0]))
        self.assertEqual(set(state["jobs"][0]["tasks"][0]), set(SAMPLE["jobs"][0]["tasks"][0]))
        self.assertEqual(set(state["workers"][0]), set(SAMPLE["workers"][0]))
        self.assertEqual(set(state["workers"][0]["current"]), set(SAMPLE["workers"][0]["current"]))
        self.assertEqual(set(state["workers"][0]["log_tail"][0]), {"at", "line"})
        self.assertEqual(set(state["packages"][0]), set(SAMPLE["packages"][0]))
        self.assertEqual(set(state["installs"][0]), set(SAMPLE["installs"][0]))

    def test_generated_at_is_utc_z(self):
        self.assertEqual(self.console().state()["generated_at"], "2026-10-23T11:21:00Z")


class Jobs(Fixture):
    def jobs(self):
        return {j["region_code"]: j for j in self.console().state()["jobs"]}

    def test_jobs_keep_db_order_newest_first(self):
        ids = [j["id"] for j in self.console().state()["jobs"]]
        self.assertEqual(ids, [JOB_APT, JOB_SONNY, JOB_PILOT])

    def test_job_fields_and_types(self):
        j = self.jobs()["OXO-APT"]
        self.assertEqual(j["revision"], 1)
        self.assertEqual(j["max_attempts"], 3)
        self.assertEqual(j["created_at"], "2026-10-23T11:08:41Z")
        self.assertEqual(j["package"], "oxo_apt")

    def test_job_states_and_counts(self):
        jobs = self.jobs()
        self.assertEqual(jobs["OXO-APT"]["state"], "in_progress")
        self.assertEqual(jobs["OXO-SONNY"]["state"], "failed")
        self.assertEqual(jobs["EU-PILOT"]["state"], "complete")
        self.assertEqual(jobs["OXO-SONNY"]["counts"],
                         {"pending": 0, "claimed": 0, "succeeded": 0, "abandoned": 2})
        self.assertEqual(jobs["OXO-SONNY"]["total"], 2)

    def test_pending_alone_is_in_progress(self):
        self.assertEqual(server.job_state({"pending": 1, "claimed": 0, "succeeded": 0, "abandoned": 1}),
                         "in_progress")

    def test_tasks_sorted_by_tile_with_nulls(self):
        tasks = self.jobs()["OXO-SONNY"]["tasks"]
        self.assertEqual([t["tile"] for t in tasks], ["+48+010", "+48+012"])
        self.assertIsNone(tasks[0]["claimed_by"])
        self.assertIsNone(tasks[0]["claimed_at"])
        self.assertEqual(tasks[0]["attempts"], 1)

    def test_csv_with_commas_quotes_newlines(self):
        t = self.jobs()["OXO-APT"]["tasks"][0]
        self.assertEqual(t["last_failure"], 'prepare: target root, "quoted"\nsecond line')
        self.assertEqual(t["claimed_at"], "2026-10-23T11:10:12Z")
        self.assertEqual(t["claimed_by"], "oxo-worker-1")

    def test_ledger_replaces_and_patches(self):
        apt = self.jobs()["OXO-APT"]["tasks"][0]
        self.assertEqual(apt["replaces"], "eu_apt (A0_EU) cfg agrees")
        self.assertEqual(apt["patches"], ["EDDM.patch.osm"])
        pilot = {t["tile"]: t for t in self.jobs()["EU-PILOT"]["tasks"]}
        self.assertIsNone(pilot["+48+010"]["replaces"])
        self.assertEqual(pilot["+48+010"]["patches"], [])
        self.assertEqual(pilot["+48+011"]["patches"], ["EDDM.patch.osm"])

    def test_job_without_ledger_record(self):
        sonny = self.jobs()["OXO-SONNY"]
        self.assertIsNone(sonny["package"])
        self.assertIsNone(sonny["tasks"][0]["replaces"])
        self.assertEqual(sonny["tasks"][0]["patches"], [])

    def test_unreachable_database(self):
        state = self.console(run=fake_run(db_fail=True)).state()
        self.assertFalse(state["database"]["reachable"])
        self.assertIn("oxo-pg", state["database"]["error"])
        self.assertEqual(state["jobs"], [])
        self.assertEqual(len(state["workers"]), 1)

    def test_reachable_database_has_null_error(self):
        self.assertEqual(self.console().state()["database"], {"reachable": True, "error": None})

    def test_psql_is_called_read_only_through_podman(self):
        calls = []
        self.console(run=fake_run(calls)).state()
        psql = [a for a, _ in calls if "psql" in a]
        self.assertEqual(len(psql), 2)
        for argv in psql:
            self.assertEqual(argv[:6], ["podman", "exec", "oxo-pg", "psql", "-U", "postgres"])
            self.assertIn("--csv", argv)
            self.assertTrue(argv[-1].lstrip().upper().startswith("SELECT"))
            self.assertIn("LIMIT 50", argv[-1])


class Installs(Fixture):
    def test_installs_newest_first_across_packages(self):
        installs = self.console().state()["installs"]
        self.assertEqual([i["at"] for i in installs],
                         ["2026-10-23T10:26:45Z", "2026-10-23T10:00:00Z", "2026-10-23T09:00:00Z"])
        self.assertEqual(installs[0], {"at": "2026-10-23T10:26:45Z", "code": "A4_PILOT",
                                       "package": "zzXEL_oxo_pilot_ortho",
                                       "tiles": ["+48+010", "+48+011", "+48+012"]})

    def test_installs_capped_at_20(self):
        write(self.ledger / "oxo_x" / "installs.log",
              "".join(f"2026-09-{d:02d}T00:00:00Z\tX\tp\t+1+1\n" for d in range(1, 26)))
        self.assertEqual(len(self.console().state()["installs"]), 20)


class Workers(Fixture):
    def worker(self, **kw):
        return self.console(run=fake_run(**kw)).state()["workers"]

    def test_only_worker_containers_without_infra(self):
        workers = self.worker()
        self.assertEqual([w["name"] for w in workers], ["oxo-worker-1-worker"])
        self.assertEqual(workers[0]["state"], "running")
        self.assertEqual(workers[0]["started_at"], "2026-10-23T08:14:23Z")

    def test_current_task_and_step(self):
        cur = self.worker()[0]["current"]
        self.assertEqual(cur, {
            "task_id": TASK_APT, "tile": "+48+011", "task_type": "ortho", "attempt": 2,
            "since": "2026-10-23T11:10:12Z",
            "step": "Step 2.5 : Building masks for tile +48+011",
            "step_since": "2026-10-23T11:15:00Z",
        })

    def test_no_current_when_last_claim_finished(self):
        logs = LOGS + f"2026-10-23T13:30:00.0+02:00 INFO oxo_worker::run: completed task {TASK_APT}\n"
        self.assertIsNone(self.worker(logs=logs)[0]["current"])

    def test_no_current_after_lease_lost(self):
        logs = LOGS + (f"2026-10-23T13:30:00.0+02:00  WARN oxo_worker::run: lease lost for task {TASK_APT}; "
                       f"killed runner, no report task={TASK_APT} why=gone\n")
        self.assertIsNone(self.worker(logs=logs)[0]["current"])

    def test_no_current_after_giving_up_on_report(self):
        logs = LOGS + ("2026-10-23T13:30:00.0+02:00 ERROR oxo_worker::run: giving up on report; "
                       f"the lease will expire task={TASK_APT} verb=\"complete\"\n")
        self.assertIsNone(self.worker(logs=logs)[0]["current"])

    def test_current_without_step_yet(self):
        logs = "2026-10-23T13:10:12.000000000+02:00 INFO oxo_worker::run: claimed task x ortho +1+002 attempt 1\n"
        cur = self.worker(logs=logs)[0]["current"]
        self.assertIsNone(cur["step"])
        self.assertIsNone(cur["step_since"])

    def test_log_tail_strips_ansi_skips_empty_and_caps_40(self):
        tail = self.worker()[0]["log_tail"]
        self.assertEqual(tail[-1], {"at": "2026-10-23T11:20:35Z",
                                    "line": "   Number of edges at this point: 124650"})
        self.assertNotIn("\x1b", json.dumps(tail))
        self.assertTrue(all(e["line"].strip() for e in tail))
        many = "".join(f"2026-10-23T13:00:{i % 60:02d}.0+02:00 line {i}\n" for i in range(100))
        tail = self.worker(logs=many)[0]["log_tail"]
        self.assertEqual(len(tail), 40)
        self.assertEqual(tail[-1]["line"], "line 99")

    def test_logs_requested_with_stderr_merged(self):
        calls = []
        self.console(run=fake_run(calls)).state()
        logs = [(a, m) for a, m in calls if a[:2] == ["podman", "logs"]]
        self.assertEqual(logs, [(["podman", "logs", "--timestamps", "--tail", str(server.LOG_LINES),
                                  "oxo-worker-1-worker"], True)])

    def test_current_survives_a_long_download_phase(self):
        # a real ZL16 ortho task logs ~790 lines between claim and completion
        downloads = "".join(f"2026-10-23T13:16:00.0+02:00 Downloading missing orthophoto {i}\n"
                            for i in range(3000))
        logs = LOGS + "2026-10-23T13:16:00.0+02:00 Step 3 : Building tile +48+011 : \n" + downloads
        cur = self.worker(logs=logs)[0]["current"]
        self.assertEqual(cur["task_id"], TASK_APT)
        self.assertEqual(cur["step"], "Step 3 : Building tile +48+011")

    def test_podman_failure_gives_no_workers(self):
        def run(argv, merge=False):
            if argv[:2] == ["podman", "ps"]:
                raise RuntimeError("podman gone")
            return fake_run()(argv, merge)
        self.assertEqual(self.console(run=run).state()["workers"], [])


class Packages(Fixture):
    def test_packages_sorted_by_code_with_owner_and_tiles(self):
        self.pkg("zzXEL_eu_sonny_ortho", "a5_EU  99.99.99", 0)
        pk = self.console().state()["packages"]
        self.assertEqual([p["code"] for p in pk], ["A0_EU", "A4_PILOT", "a5_EU", "EU-WEST"])
        by = {p["name"]: p for p in pk}
        self.assertEqual(by["zzXEL_eu-west_ortho"],
                         {"name": "zzXEL_eu-west_ortho", "code": "EU-WEST", "version": "0.5.0",
                          "tiles": 2, "owner": "samsoir"})
        self.assertEqual(by["zzXEL_oxo_pilot_ortho"]["owner"], "oxo")
        self.assertEqual(by["zzXEL_eu_apt_ortho"]["owner"], "own")
        self.assertEqual(by["zzXEL_oxo_pilot_ortho"]["tiles"], 3)

    def test_missing_packages_dir_is_empty(self):
        c = server.Console(run=fake_run(), ledger_dir=self.ledger,
                           packages_dir=self.packages / "nope", clock=lambda: 0.0)
        self.assertEqual(c.state()["packages"], [])


class Caching(Fixture):
    def test_state_and_packages_cached_2s(self):
        # packages refresh with installs, else a fresh install looks like a removed package
        now = [1000.0]
        calls = []
        c = self.console(run=fake_run(calls), clock=lambda: now[0])
        c.state()
        n = len(calls)
        now[0] += 1.5
        c.state()
        self.assertEqual(len(calls), n)
        self.pkg("zzXEL_new_ortho", "B_NEW  1.0.0", 1)
        now[0] += 1.0
        self.assertEqual(len(c.state()["packages"]), 4)
        self.assertGreater(len(calls), n)


class Helpers(unittest.TestCase):
    def test_iso_from_log_timestamp(self):
        self.assertEqual(server.iso_utc("2026-10-23T13:10:34.605678000+02:00"), "2026-10-23T11:10:34Z")

    def test_iso_from_unix(self):
        self.assertEqual(server.iso_unix(1792743263), "2026-10-23T08:14:23Z")


class Http(Fixture):
    def serve(self, static):
        srv = server.make_server("127.0.0.1", 0, self.console(), static)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_api_state(self):
        base = self.serve(pathlib.Path(self.tmp.name) / "static")
        with urllib.request.urlopen(base + "/api/state") as r:
            self.assertEqual(r.headers["Content-Type"], "application/json")
            self.assertEqual(r.headers["Cache-Control"], "no-store")
            self.assertEqual(set(json.load(r)), set(SAMPLE))

    def test_placeholder_without_index(self):
        base = self.serve(pathlib.Path(self.tmp.name) / "static")
        with urllib.request.urlopen(base + "/") as r:
            self.assertEqual(r.status, 200)
            self.assertIn(b"/api/state", r.read())

    def test_serves_static_index(self):
        static = pathlib.Path(self.tmp.name) / "static"
        write(static / "index.html", "<p>console</p>")
        base = self.serve(static)
        with urllib.request.urlopen(base + "/") as r:
            self.assertEqual(r.read(), b"<p>console</p>")


if __name__ == "__main__":
    unittest.main()
