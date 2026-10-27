"""Fixtures for race tests. They talk to the REAL running stack over HTTP (API_URL) and use the database directly only to
create isolated test flights and to assert invariants. Env: API_URL, POSTGRES_*, PG_TEST_HOST/PORT, REDIS_URL."""
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest
import pytest_asyncio

API_URL = os.getenv("API_URL", "http://localhost:8080")
PG = dict(host=os.getenv("PG_TEST_HOST", "coordinator"), port=int(os.getenv("PG_TEST_PORT", "5432")),
          user=os.getenv("POSTGRES_USER", "ars"), password=os.getenv("POSTGRES_PASSWORD", ""), database=os.getenv("POSTGRES_DB", "ars"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


@pytest_asyncio.fixture
async def db():
    c = await asyncpg.connect(**PG)
    yield c
    await c.close()


@pytest_asyncio.fixture
async def http():
    async with httpx.AsyncClient(base_url=API_URL, timeout=30, limits=httpx.Limits(max_connections=200)) as c:
        yield c


@pytest_asyncio.fixture
async def redis_client():
    import redis.asyncio as aioredis
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    await r.aclose()


async def register(http, prefix="rt") -> dict:
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    r = await http.post("/v1/auth/register", json={"username": name, "email": f"{name}@test.local", "password": "Passw0rd!x"})
    assert r.status_code == 201, r.text
    j = r.json()
    return {"id": j["user_id"], "name": name, "h": {"Authorization": f"Bearer {j['access_token']}"}}


@pytest_asyncio.fixture
async def users(http):
    async def make(n: int):
        out = []
        for i in range(0, n, 10):  # register in small batches (bcrypt is CPU heavy)
            import asyncio
            out += await asyncio.gather(*[register(http) for _ in range(min(10, n - i))])
        return out
    return make


@pytest_asyncio.fixture
async def make_flight(db):
    """Create an isolated flight (aircraft 1: 12 business, 6 premium, 78 economy seats) where exactly `free` economy seats are
    unsold: the first `free` economy seats. Everything else is sold, so inventory and the seat map agree."""
    created = []

    async def make(free: int) -> tuple[int, list[str]]:
        fid = random.randint(800_000_000, 890_000_000)
        dep = datetime.now(timezone.utc) + timedelta(days=2)
        ac = await db.fetchrow("SELECT * FROM aircraft_types WHERE aircraft_id = 1")
        br, pr, er = ac["business_rows"], ac["premium_rows"], ac["economy_rows"]
        lay = {"BUSINESS": [f"{r}{c}" for r in range(1, br + 1) for c in "ABCDEF"],
               "PREMIUM": [f"{r}{c}" for r in range(br + 1, br + pr + 1) for c in "ABCDEF"],
               "ECONOMY": [f"{r}{c}" for r in range(br + pr + 1, br + pr + er + 1) for c in "ABCDEF"]}
        await db.execute("INSERT INTO flights VALUES ($1,$2,1,1,2,1,$3,$4,420,0,100.00,$5,NULL)", fid, "RT" + str(fid)[-4:], dep, dep + timedelta(hours=7), free)
        for cls, mult in (("BUSINESS", 3.2), ("PREMIUM", 1.8), ("ECONOMY", 1.0)):
            await db.execute("INSERT INTO seat_inventory VALUES ($1,$2,$3,$4,$5)", fid, cls, len(lay[cls]), free if cls == "ECONOMY" else 0, round(100 * mult, 2))
        free_seats = lay["ECONOMY"][:free]
        sold = [(fid, s, c) for c, ss in lay.items() for s in ss if s not in free_seats]
        await db.executemany("INSERT INTO seats VALUES ($1,$2,$3,'TESTSD',1)", sold)
        created.append(fid)
        return fid, free_seats

    yield make
    for fid in created:  # tidy up so reruns stay clean
        for t in ("outbox", "tickets", "seats", "bookings", "seat_inventory", "flights"):
            await db.execute(f"DELETE FROM {t} WHERE flight_id = $1", fid)  # noqa: S608 fixed literals


async def hold(http, user, fid, seats):
    return await http.post("/v1/holds", json={"flight_id": fid, "seats": seats}, headers=user["h"])


async def book(http, user, fid, hold_id, seats, key=None):
    return await http.post("/v1/bookings", json={"flight_id": fid, "hold_id": hold_id, "passengers": [{"name": f"P {s}", "seat_no": s} for s in seats]},
                           headers={**user["h"], "Idempotency-Key": key or uuid.uuid4().hex})


async def assert_invariants(db, fid):
    inv = await db.fetch("SELECT fare_class, total, available FROM seat_inventory WHERE flight_id=$1", fid)
    assert all(r["available"] >= 0 for r in inv), "negative inventory"
    for r in inv:
        sold = await db.fetchval("SELECT count(*) FROM seats WHERE flight_id=$1 AND fare_class=$2", fid, r["fare_class"])
        assert r["total"] - r["available"] == sold, f"{r['fare_class']}: inventory disagrees with seats table"
    dup = await db.fetchval("SELECT count(*) FROM (SELECT seat_no FROM seats WHERE flight_id=$1 GROUP BY 1 HAVING count(*)>1) x", fid)
    assert dup == 0, "double-booked seat"
    left = await db.fetchval("SELECT seats_left FROM flights WHERE flight_id=$1", fid)
    assert left == sum(r["available"] for r in inv), "flights.seats_left drifted"
