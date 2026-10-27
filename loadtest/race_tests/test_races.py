"""Automated race tests (RULES.md testing rules). Each asserts: 0 double bookings, 0 negative inventory."""
import asyncio
import random
import uuid

import pytest

from .conftest import assert_invariants, book, hold, register

pytestmark = pytest.mark.asyncio


async def test_same_seat_two_holds_one_winner(http, db, users, make_flight):
    """Two customers hold the SAME seat at the same instant: Redis Lua makes exactly one win."""
    fid, free = await make_flight(5)
    a, b = await users(2)
    ra, rb = await asyncio.gather(hold(http, a, fid, [free[0]]), hold(http, b, fid, [free[0]]))
    assert sorted([ra.status_code, rb.status_code]) == [201, 409], (ra.text, rb.text)
    loser = ra if ra.status_code == 409 else rb
    assert loser.json()["error"] == "SEAT_CONFLICT"
    await assert_invariants(db, fid)


async def test_same_seat_two_confirms_db_guard(http, db, users, make_flight):
    """Redis bypassed ('dbfallback' holds): the PostgreSQL guards alone must still allow only one booking of the seat."""
    fid, free = await make_flight(5)
    a, b = await users(2)
    ra, rb = await asyncio.gather(book(http, a, fid, "dbfallback:x", [free[0]]), book(http, b, fid, "dbfallback:y", [free[0]]))
    assert sorted([ra.status_code, rb.status_code]) == [201, 409], (ra.text, rb.text)
    assert (ra if ra.status_code == 409 else rb).json()["error"] in ("SEAT_CONFLICT", "SEAT_UNAVAILABLE")
    await assert_invariants(db, fid)
    assert await db.fetchval("SELECT count(*) FROM bookings WHERE flight_id=$1", fid) == 1


async def test_last_seat_many_buyers(http, db, users, make_flight):
    """1 seat left, 20 buyers race for it at the DB level: exactly one wins, available ends at 0, never -1."""
    fid, free = await make_flight(1)
    us = await users(20)
    rs = await asyncio.gather(*[book(http, u, fid, f"dbfallback:{i}", [free[0]]) for i, u in enumerate(us)])
    codes = [r.status_code for r in rs]
    assert codes.count(201) == 1 and codes.count(409) == 19, codes
    assert await db.fetchval("SELECT available FROM seat_inventory WHERE flight_id=$1 AND fare_class='ECONOMY'", fid) == 0
    assert await db.fetchval("SELECT seats_left FROM flights WHERE flight_id=$1", fid) == 0
    await assert_invariants(db, fid)


async def test_last_seat_via_holds_and_confirm(http, db, users, make_flight):
    """Full path (Redis hold then confirm) with 10 buyers on the last seat: one hold wins and its booking succeeds."""
    fid, free = await make_flight(1)
    us = await users(10)
    hs = await asyncio.gather(*[hold(http, u, fid, [free[0]]) for u in us])
    winners = [(u, h) for u, h in zip(us, hs) if h.status_code == 201]
    assert len(winners) == 1 and all(h.status_code in (201, 409) for h in hs)
    u, h = winners[0]
    r = await book(http, u, fid, h.json()["hold_id"], [free[0]])
    assert r.status_code == 201, r.text
    await assert_invariants(db, fid)


async def test_n_seats_m_buyers(http, db, users, make_flight):
    """5 free seats, 30 buyers each grabbing a random free seat: exactly 5 bookings, inventory exactly 0, no seat sold twice."""
    fid, free = await make_flight(5)
    us = await users(30)
    rs = await asyncio.gather(*[book(http, u, fid, f"dbfallback:{i}", [random.choice(free)]) for i, u in enumerate(us)])
    codes = [r.status_code for r in rs]
    # random picks may collide, so up to 5 succeed; whoever lost must have got a clean 409, never a 5xx
    assert codes.count(201) <= 5 and all(c in (201, 409) for c in codes), codes
    # now fill whatever is left deterministically and confirm the flight sells out EXACTLY
    remaining = await db.fetch("SELECT seat_no FROM seats WHERE flight_id=$1", fid)
    taken = {x["seat_no"] for x in remaining}
    left = [s for s in free if s not in taken]
    rs2 = await asyncio.gather(*[book(http, us[i], fid, f"dbfallback:z{i}", [s]) for i, s in enumerate(left)])
    assert all(r.status_code == 201 for r in rs2), [r.text for r in rs2]
    assert await db.fetchval("SELECT available FROM seat_inventory WHERE flight_id=$1 AND fare_class='ECONOMY'", fid) == 0
    extra = await book(http, us[-1], fid, "dbfallback:over", [free[0]])
    assert extra.status_code == 409
    await assert_invariants(db, fid)


async def test_idempotent_retry(http, db, users, make_flight):
    """Same Idempotency-Key sent 6x concurrently (client retry storm): one booking, identical PNR, inventory decremented once."""
    fid, free = await make_flight(3)
    (u,) = await users(1)
    h = (await hold(http, u, fid, [free[0]])).json()
    key = uuid.uuid4().hex
    rs = await asyncio.gather(*[book(http, u, fid, h["hold_id"], [free[0]], key=key) for _ in range(6)])
    assert all(r.status_code == 201 for r in rs), [r.text for r in rs]
    assert len({r.json()["pnr"] for r in rs}) == 1
    assert await db.fetchval("SELECT count(*) FROM bookings WHERE flight_id=$1", fid) == 1
    assert await db.fetchval("SELECT available FROM seat_inventory WHERE flight_id=$1 AND fare_class='ECONOMY'", fid) == 2
    again = await book(http, u, fid, h["hold_id"], [free[0]], key=key)  # a later replay still returns the original
    assert again.json()["pnr"] == rs[0].json()["pnr"] and again.json()["idempotent_replay"] is True
    await assert_invariants(db, fid)


async def test_hold_expiry(http, db, users, make_flight, redis_client):
    """A hold whose TTL passes frees the seat for someone else; the expired holder gets 410 HOLD_EXPIRED."""
    fid, free = await make_flight(3)
    a, b = await users(2)
    ha = (await hold(http, a, fid, [free[0]])).json()
    assert (await redis_client.ttl(f"hold:{fid}:{free[0]}")) > 500          # 10 minute TTL
    await redis_client.expire(f"hold:{fid}:{free[0]}", 1)                     # fast-forward the TTL
    await asyncio.sleep(2.2)
    rb = await hold(http, b, fid, [free[0]])
    assert rb.status_code == 201, rb.text                                     # seat is free again
    late = await book(http, a, fid, ha["hold_id"], [free[0]])
    assert late.status_code == 410 and late.json()["error"] == "HOLD_EXPIRED"
    ok = await book(http, b, fid, rb.json()["hold_id"], [free[0]])
    assert ok.status_code == 201
    await assert_invariants(db, fid)


async def test_duplicate_registration_race(http):
    """20 concurrent signups for one username: the registry PRIMARY KEY lets exactly one through; the rest get 409."""
    name = f"dup_{uuid.uuid4().hex[:10]}"
    rs = await asyncio.gather(*[http.post("/v1/auth/register", json={"username": name, "email": f"{i}_{name}@t.local", "password": "Passw0rd!x"}) for i in range(20)])
    codes = [r.status_code for r in rs]
    assert codes.count(201) == 1 and codes.count(409) == 19, codes
    assert all(r.json()["error"] == "USERNAME_TAKEN" for r in rs if r.status_code == 409)
    av = (await http.get("/v1/users/availability", params={"username": name})).json()
    assert av["username"]["available"] is False


async def test_duplicate_email_race(http):
    mail = f"{uuid.uuid4().hex[:10]}@t.local"
    rs = await asyncio.gather(*[http.post("/v1/auth/register", json={"username": f"em_{uuid.uuid4().hex[:10]}", "email": mail, "password": "Passw0rd!x"}) for _ in range(15)])
    codes = [r.status_code for r in rs]
    assert codes.count(201) == 1 and codes.count(409) == 14, codes


async def test_cancel_releases_seat(http, db, users, make_flight):
    fid, free = await make_flight(2)
    a, b = await users(2)
    h = (await hold(http, a, fid, [free[0]])).json()
    bk = (await book(http, a, fid, h["hold_id"], [free[0]])).json()
    assert await db.fetchval("SELECT available FROM seat_inventory WHERE flight_id=$1 AND fare_class='ECONOMY'", fid) == 1
    assert (await http.delete(f"/v1/bookings/{fid}/{bk['pnr']}", headers=b["h"])).status_code == 404   # not b's booking
    c = await http.delete(f"/v1/bookings/{fid}/{bk['pnr']}", headers=a["h"])
    assert c.status_code == 200 and c.json()["status"] == "CANCELLED"
    assert (await http.delete(f"/v1/bookings/{fid}/{bk['pnr']}", headers=a["h"])).status_code == 404  # no double cancel
    assert await db.fetchval("SELECT available FROM seat_inventory WHERE flight_id=$1 AND fare_class='ECONOMY'", fid) == 2
    h2 = await hold(http, b, fid, [free[0]])
    assert h2.status_code == 201
    await assert_invariants(db, fid)


async def test_hold_on_sold_seat_is_409(http, db, users, make_flight):
    fid, free = await make_flight(1)
    (u,) = await users(1)
    r = await hold(http, u, fid, ["1A"])  # business seat, sold by the fixture
    assert r.status_code == 409 and r.json()["error"] == "SEAT_UNAVAILABLE"


async def test_global_invariants(db):
    assert await db.fetchval("SELECT count(*) FROM seat_inventory WHERE available < 0") == 0
    assert await db.fetchval("SELECT count(*) FROM (SELECT flight_id, seat_no FROM seats GROUP BY 1,2 HAVING count(*) > 1) x") == 0
