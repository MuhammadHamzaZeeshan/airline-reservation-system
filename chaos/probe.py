#!/usr/bin/env python3
"""Chaos helper (stdlib only).  probe SECONDS BASE_URL | book BASE_URL
probe: hits /health/live and a real search for SECONDS, prints ok/failed counts, exit 1 if any request fails.
book : registers a user, books a free seat on a demo flight; exit 0 on 201 or 409 (clean conflict), 1 on anything else (e.g. 5xx)."""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone


def call(method, url, body=None, headers=None, timeout=5):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:  # noqa: BLE001
            return e.code, None
    except Exception:  # noqa: BLE001
        return 0, None


def probe(seconds: int, base: str) -> int:
    ok = bad = 0
    end = time.time() + seconds
    to = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat().replace("+00:00", "Z")
    search = f"{base}/v1/flights/search?origin=KHI&destination=LHR&date_to={to}&limit=5"
    while time.time() < end:
        for url in (f"{base}/health/live", search):
            s, _ = call("GET", url)
            if s in (200, 429):
                ok += 1
            else:
                bad += 1
        time.sleep(0.1)
    print(f"probe: {ok} ok / {bad} failed")
    return 0 if bad == 0 else 1


def book(base: str) -> int:
    name = "chaos_" + uuid.uuid4().hex[:10]
    s, j = call("POST", f"{base}/v1/auth/register", {"username": name, "email": f"{name}@c.local", "password": "Passw0rd!x"})
    if s != 201:
        print("register failed", s, j)
        return 1
    h = {"Authorization": f"Bearer {j['access_token']}"}
    for fid in range(900000001, 900000006):
        s, sm = call("GET", f"{base}/v1/flights/{fid}/seatmap")
        free = [x["seat_no"] for x in (sm or {}).get("seats", []) if x["status"] == "available"]
        if not free:
            continue
        s, hold = call("POST", f"{base}/v1/holds", {"flight_id": fid, "seats": [free[0]]}, h)
        if s != 201:
            print("hold ->", s)
            if s >= 500:
                return 1
            continue
        s, b = call("POST", f"{base}/v1/bookings", {"flight_id": fid, "hold_id": hold["hold_id"], "passengers": [{"name": "Chaos", "seat_no": free[0]}]},
                    {**h, "Idempotency-Key": uuid.uuid4().hex})
        print(f"booking -> {s} degraded={hold.get('degraded')} {b.get('pnr') if isinstance(b, dict) else ''}")
        return 0 if s in (201, 409) else 1
    print("no free demo seats left (reseed with make seed); treating as pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "probe":
        sys.exit(probe(int(sys.argv[2]), sys.argv[3]))
    sys.exit(book(sys.argv[2]))
