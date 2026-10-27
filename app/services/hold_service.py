"""Seat holds in Redis (advisory, TTL 10 min). PostgreSQL remains the truth at confirm time.

Atomicity: ONE Lua script checks every requested seat and only then sets them all (all-or-nothing, no partial holds) and adjusts the
per-class availability counters. Redis runs scripts single-threaded, so two buyers of the same seat get exactly one winner.
Failure behaviour: if Redis is unreachable the hold endpoint returns a 'dbfallback:' hold and the DB guards at confirm decide.
"""
import json
import time
import uuid

from prometheus_client import Counter

from app.core.errors import ApiError
from app.services import inventory as inv
from app.services.layout import class_of

HOLDS = Counter("holds_total", "seat hold attempts", ["result"])

HOLD_LUA = """
local n=tonumber(ARGV[3])
for i=1,n do if redis.call('EXISTS',KEYS[i])==1 then return i end end
for i=1,n do redis.call('SET',KEYS[i],ARGV[1],'EX',ARGV[2]) end
local m=#KEYS-n
for j=1,m do local k=KEYS[n+j]; if redis.call('EXISTS',k)==1 then redis.call('DECRBY',k,ARGV[3+j]) end end
return 0
"""
# compare-and-delete: only remove seat keys that still belong to this hold; give counters back only for seats we really released
RELEASE_LUA = """
local n=tonumber(ARGV[2]); local freed={}
for i=1,n do if redis.call('GET',KEYS[i])==ARGV[1] then redis.call('DEL',KEYS[i]); freed[#freed+1]=i end end
return #freed
"""


def seat_key(fid: int, seat: str) -> str:
    return f"hold:{fid}:{seat}"


async def create_hold(app, user, flight_id: int, seats: list[str]) -> dict:
    st = app.state
    pool, r, s = st.pg_pool, st.redis, st.settings
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    fl = await inv.get_flight(pool, flight_id)
    classes = {}
    for seat in seats:
        c = class_of(seat, fl["br"], fl["pr"], fl["er"])
        if c is None:
            raise ApiError(400, "VALIDATION_ERROR", f"seat {seat} does not exist on this aircraft")
        classes[seat] = c
    # the database is the truth for sold seats
    sold = await pool.fetch("SELECT seat_no FROM seats WHERE flight_id = $1 AND seat_no = ANY($2::text[])", flight_id, seats)
    if sold:
        HOLDS.labels("sold").inc()
        raise ApiError(409, "SEAT_UNAVAILABLE", f"seat {sold[0]['seat_no']} is already booked")
    prices = await inv.db_inventory(pool, flight_id)
    by_class: dict[str, int] = {}
    for c in classes.values():
        by_class[c] = by_class.get(c, 0) + 1
    total = round(sum(prices[c]["price"] * n for c, n in by_class.items()), 2)
    ttl = s.hold_ttl_seconds
    expires = int(time.time()) + ttl

    if r is None:
        return _fallback(flight_id, seats, total, ttl)
    hold_id = uuid.uuid4().hex
    try:
        await inv.ensure_counters(pool, r, flight_id, prices)
        cls_list = sorted(by_class)
        keys = [seat_key(flight_id, x) for x in seats] + [inv.ckey(flight_id, c) for c in cls_list]
        res = await r.eval(HOLD_LUA, len(keys), *keys, hold_id, ttl, len(seats), *[by_class[c] for c in cls_list])
        if res != 0:
            HOLDS.labels("conflict").inc()
            raise ApiError(409, "SEAT_CONFLICT", f"seat {seats[int(res) - 1]} is held by another customer")
        meta = {"hold_id": hold_id, "user_id": user.user_id, "flight_id": flight_id, "seats": seats, "classes": classes,
                "by_class": by_class, "expires": expires, "total": total}
        pipe = r.pipeline()
        pipe.set(f"holdmeta:{hold_id}", json.dumps(meta), ex=ttl + 120)
        pipe.zadd("holds:expiry", {hold_id: expires})
        pipe.sadd(f"flightholds:{flight_id}", hold_id)
        await pipe.execute()
    except ApiError:
        raise
    except Exception:  # noqa: BLE001 Redis failure -> degrade to DB-only guards
        HOLDS.labels("degraded").inc()
        return _fallback(flight_id, seats, total, ttl)
    HOLDS.labels("ok").inc()
    return {"hold_id": hold_id, "flight_id": flight_id, "seats": seats, "expires_at": expires, "ttl_seconds": ttl,
            "total_price": total, "degraded": False}


def _fallback(flight_id: int, seats: list[str], total: float, ttl: int) -> dict:
    return {"hold_id": f"dbfallback:{uuid.uuid4().hex}", "flight_id": flight_id, "seats": seats, "expires_at": int(time.time()) + ttl,
            "ttl_seconds": ttl, "total_price": total, "degraded": True}


async def verify_hold(r, hold_id: str, user_id: int, flight_id: int, seats: list[str]) -> None:
    """410 HOLD_EXPIRED unless the hold exists, is ours, matches the seats, and every seat key still carries our hold id."""
    meta_raw = await r.get(f"holdmeta:{hold_id}")
    if not meta_raw:
        raise ApiError(410, "HOLD_EXPIRED", "hold expired or not found")
    m = json.loads(meta_raw)
    if m["user_id"] != user_id or m["flight_id"] != flight_id:
        raise ApiError(409, "SEAT_CONFLICT", "hold belongs to someone else")
    if set(m["seats"]) != set(seats):
        raise ApiError(400, "VALIDATION_ERROR", "passenger seats must match the held seats")
    vals = await r.mget([seat_key(flight_id, x) for x in seats])
    if any(v != hold_id for v in vals):
        raise ApiError(410, "HOLD_EXPIRED", "hold expired")


async def release(app, hold_id: str, user_id: int | None = None, give_back: bool = True) -> bool:
    r = app.state.redis
    if r is None or hold_id.startswith("dbfallback:"):
        return True
    raw = await r.get(f"holdmeta:{hold_id}")
    if not raw:
        return False
    m = json.loads(raw)
    if user_id is not None and m["user_id"] != user_id:
        raise ApiError(403, "FORBIDDEN", "not your hold")
    fid = m["flight_id"]
    keys = [seat_key(fid, x) for x in m["seats"]]
    await r.eval(RELEASE_LUA, len(keys), *keys, hold_id, len(keys))
    if give_back and await r.zrem("holds:expiry", hold_id):  # exactly one party (us or the reconciler) returns the counters
        for c, n in m["by_class"].items():
            if await r.exists(inv.ckey(fid, c)):
                await r.incrby(inv.ckey(fid, c), n)
    await r.zrem("holds:expiry", hold_id)
    await r.srem(f"flightholds:{fid}", hold_id)
    await r.delete(f"holdmeta:{hold_id}")
    return True


async def finish_after_confirm(app, hold_id: str, flight_id: int, seats: list[str]) -> None:
    """Booking committed: drop the hold WITHOUT returning counters (the seats are really sold now)."""
    r = app.state.redis
    if r is None or hold_id.startswith("dbfallback:"):
        return
    try:
        await r.zrem("holds:expiry", hold_id)
        await r.srem(f"flightholds:{flight_id}", hold_id)
        await r.delete(f"holdmeta:{hold_id}", *[seat_key(flight_id, x) for x in seats])
    except Exception:  # noqa: BLE001 - keys expire on their own TTL
        pass
