"""Simulation controller sidecar for the admin panel. Stdlib only. Runs a WHITELIST of docker/k6/pytest commands - nothing user-supplied
ever reaches a shell. Protected by a shared token; only the API (admin-authenticated) calls it. It has the Docker socket: demo use only."""
import json
import os
import subprocess
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("SIMCTL_TOKEN", "")
EDGE = os.environ.get("EDGE_URL", "http://nginx:80")
JOBS: dict[str, dict] = {}


def probe(seconds: int, log):
    ok = bad = 0
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(f"{EDGE}/health/live", timeout=2).read()
            ok += 1
        except Exception:  # noqa: BLE001
            bad += 1
        time.sleep(0.2)
    log(f"availability probe: {ok} ok / {bad} failed through the load balancer")


def sh(cmd: list[str], log):
    log("$ " + " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        log(line.rstrip())
    return p.wait()


def run_job(job_id: str, name: str):
    j = JOBS[job_id]
    log = lambda s: j["log"].append(s)  # noqa: E731
    try:
        if name == "load-test":
            sh(["docker", "exec", "ars-k6", "k6", "run", "--quiet", "/scripts/baseline.js"], log)
        elif name == "heavy-load":
            sh(["docker", "exec", "ars-k6", "k6", "run", "--quiet", "/scripts/heavy.js"], log)
        elif name == "race-test":
            sh(["docker", "exec", "-w", "/srv", "-e", f"API_URL={EDGE}", "-e", "PG_TEST_HOST=coordinator", "ars-api1", "python", "-m", "pytest", "loadtest/race_tests", "-q", "--no-header"], log)
        elif name == "kill-api":
            sh(["docker", "stop", "ars-api1"], log)
            probe(15, log)
            sh(["docker", "start", "ars-api1"], log)
        elif name == "kill-worker":
            sh(["docker", "stop", "ars-worker2"], log)
            probe(15, log)
            sh(["docker", "start", "ars-worker2"], log)
        elif name == "restore-all":
            for c in ("ars-api1", "ars-api2", "ars-redis", "ars-worker1", "ars-worker2", "ars-coordinator"):
                sh(["docker", "start", c], log)
        j["status"] = "done"
    except Exception as e:  # noqa: BLE001
        log(f"error: {e}")
        j["status"] = "failed"


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        if not TOKEN or self.headers.get("X-Token") != TOKEN:
            self._send(401, {"error": "bad token"})
            return False
        return True

    def do_POST(self):
        if not self._auth():
            return
        if self.path.startswith("/run/"):
            name = self.path[5:]
            if name not in {"load-test", "heavy-load", "race-test", "kill-api", "kill-worker", "restore-all"}:
                return self._send(400, {"error": "unknown job"})
            jid = uuid.uuid4().hex[:10]
            JOBS[jid] = {"status": "running", "log": [], "name": name}
            threading.Thread(target=run_job, args=(jid, name), daemon=True).start()
            return self._send(200, {"job_id": jid, "name": name})
        self._send(404, {"error": "not found"})

    def do_GET(self):
        if not self._auth():
            return
        if self.path.startswith("/log/"):
            j = JOBS.get(self.path[5:])
            return self._send(200, {"status": j["status"], "lines": j["log"][-400:]} if j else {"status": "unknown", "lines": []})
        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), H).serve_forever()
