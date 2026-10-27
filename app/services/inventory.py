"""Shared flight/inventory lookups + Redis availability counters (advisory; PostgreSQL decides at confirm)."""
import json

from prometheus_client import Counter

from app.core.errors import ApiError
from app.services.layout import all_seats

CACHE = Counter("availability_cache_total", "availability counter lookups", ["result"])
CLASSES = ("BUSINESS", "PREMIUM", "ECONOMY")


def ckey(fid: int, cls: str) -> str:
    return f"avail:{fid}:{cls}"


async def get_flight(pool, flight_id: int):
    row = await pool.fetchrow(
        """SELECT f.flight_id, f.flight_no, f.departure_ts, f.arrival_ts, f.origin_id, f.dest_id, f.price, f.seats_left,
                  a.business_rows AS br, a.premium_rows AS pr, a.economy_rows AS er
           FROM flights f JOIN aircraft_types a ON a.aircraft_id = f.aircraft_id WHERE f.flight_id = $1""", flight_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "flight not found")
    return row


async def db_inventory(pool, flight_id: int) -> dict[str, dict]:
    rows = await pool.fetch("SELECT fare_class, total, available, price FROM seat_inventory WHERE flight_id = $1", flight_id)
    return {r["fare_class"]: {"total": r["total"], "available": r["available"], "price": float(r["price"])} for r in rows}


async def held_by_class(r, flight_id: int) -> dict[str, int]:
    held: dict[str, int] = {}
    for hid in await r.smembers(f"flightholds:{flight_id}"):
        meta = await r.get(f"holdmeta:{hid}")
        if meta:
            m = json.loads(meta)
            for cls, n in m["by_class"].items():
                held[cls] = held.get(cls, 0) + n
    return held


async def ensure_counters(pool, r, flight_id: int, inv: dict | None = None) -> dict[str, int]:
    """Counters = DB available minus seats currently held. Seeded with SET NX so concurrent seeders agree."""
    inv = inv or await db_inventory(pool, flight_id)
    keys = [ckey(flight_id, c) for c in CLASSES]
    vals = await r.mget(keys)
    if all(v is not None for v in vals):
        CACHE.labels("hit").inc()
        return {c: int(v) for c, v in zip(CLASSES, vals)}
    CACHE.labels("miss").inc()
    held = await held_by_class(r, flight_id)
    out = {}
    for c in CLASSES:
        n = max(0, inv.get(c, {}).get("available", 0) - held.get(c, 0))
        await r.set(ckey(flight_id, c), n, ex=3600, nx=True)
        out[c] = int(await r.get(ckey(flight_id, c)) or n)
    return out


async def availability(app, flight_id: int) -> dict:
    pool, r = app.state.pg_pool, app.state.redis
    fl = await get_flight(pool, flight_id)
    inv = await db_inventory(pool, flight_id)
    source, counters = "database", None
    if r is not None:
        try:
            counters = await ensure_counters(pool, r, flight_id, inv)
            source = "cache"
        except Exception:  # noqa: BLE001  Redis down -> read straight from the DB (still correct)
            counters = None
    classes = []
    for c in CLASSES:
        i = inv.get(c)
        if not i or i["total"] == 0:
            continue
        classes.append({"fare_class": c, "total": i["total"], "available": counters[c] if counters else i["available"],
                        "db_available": i["available"], "price": i["price"]})
    return {"flight_id": flight_id, "flight_no": fl["flight_no"], "source": source, "classes": classes}


async def seat_map(app, flight_id: int) -> dict:
    pool, r = app.state.pg_pool, app.state.redis
    fl = await get_flight(pool, flight_id)
    seats = all_seats(fl["br"], fl["pr"], fl["er"])
    booked = {x["seat_no"] for x in await pool.fetch("SELECT seat_no FROM seats WHERE flight_id = $1", flight_id)}
    held: set[str] = set()
    if r is not None:
        try:
            free = [s for s, _ in seats if s not in booked]
            vals = await r.mget([f"hold:{flight_id}:{s}" for s in free])
            held = {s for s, v in zip(free, vals) if v is not None}
        except Exception:  # noqa: BLE001
            held = set()
    inv = await db_inventory(pool, flight_id)
    return {
        "flight_id": flight_id, "layout": "3-3", "letters": list("ABCDEF"),
        "classes": [{"fare_class": c, "price": inv.get(c, {}).get("price")} for c in CLASSES],
        "seats": [{"seat_no": s, "fare_class": c, "status": "booked" if s in booked else "held" if s in held else "available"} for s, c in seats],
    }
