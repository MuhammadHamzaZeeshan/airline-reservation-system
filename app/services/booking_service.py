"""Booking engine. EVERYTHING in one booking touches ONE shard (all tables are co-located on flight_id), so the confirm step is
a plain single-node ACID transaction - no two-phase commit.

Guards (any failure => ROLLBACK => 409, nothing partial survives):
  1. INSERT booking ... ON CONFLICT DO NOTHING        -> UNIQUE(flight_id, idempotency_key): replays return the first result
  2. INSERT seat    ... ON CONFLICT DO NOTHING        -> PK(flight_id, seat_no): a seat can be sold only once, rowcount checked
  3. UPDATE seat_inventory SET available=available-n WHERE available >= n   -> never negative (plus CHECK constraint)
  4. UPDATE flights SET seats_left=seats_left-n WHERE seats_left >= n
  5. INSERT tickets + outbox row (same transaction => the event exists iff the booking exists)
Redis holds are advisory: they are verified first for a good error message, but the DB guards are what guarantees correctness.
"""
import json
import secrets
from datetime import datetime, timezone

import asyncpg
from prometheus_client import Counter

from app.core.errors import ApiError
from app.schemas.models import BookingIn
from app.services import hold_service, inventory as inv
from app.services.layout import class_of

BOOKINGS = Counter("bookings_total", "booking confirm attempts", ["result"])
B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


class _Pnr(Exception):
    pass


def new_pnr() -> str:
    return "".join(secrets.choice(B32) for _ in range(6))


async def _replay(conn, flight_id: int, ikey: str):
    b = await conn.fetchrow("SELECT pnr, status, total_price FROM bookings WHERE flight_id=$1 AND idempotency_key=$2", flight_id, ikey)
    if b is None:
        return None
    t = await conn.fetch("SELECT ticket_no, seat_no, fare_class, passenger_name, price FROM tickets WHERE flight_id=$1 AND pnr=$2 ORDER BY seat_no", flight_id, b["pnr"])
    return {"pnr": b["pnr"], "flight_id": flight_id, "status": b["status"], "total_price": float(b["total_price"]), "idempotent_replay": True,
            "tickets": [{**dict(x), "price": float(x["price"])} for x in t]}


async def confirm(app, user, body: BookingIn, idem_key: str | None) -> dict:
    st = app.state
    pool, r = st.pg_pool, st.redis
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    if not idem_key or not (8 <= len(idem_key) <= 100):
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key header (8-100 chars) is required")
    fid = body.flight_id
    ikey = f"{user.user_id}:{idem_key}"

    async with pool.acquire() as c:  # a retry after a crash/failover returns the original booking
        prior = await _replay(c, fid, ikey)
    if prior:
        BOOKINGS.labels("replay").inc()
        return prior

    seats = sorted(p.seat_no for p in body.passengers)
    if len(set(seats)) != len(seats):
        raise ApiError(400, "VALIDATION_ERROR", "duplicate seats")
    if len(seats) > st.settings.max_seats_per_booking:
        raise ApiError(400, "VALIDATION_ERROR", "too many seats")
    fl = await inv.get_flight(pool, fid)
    if fl["departure_ts"] <= datetime.now(timezone.utc):
        raise ApiError(400, "VALIDATION_ERROR", "flight has already departed")
    classes = {}
    for sno in seats:
        cl = class_of(sno, fl["br"], fl["pr"], fl["er"])
        if cl is None:
            raise ApiError(400, "VALIDATION_ERROR", f"seat {sno} does not exist")
        classes[sno] = cl

    degraded = body.hold_id.startswith("dbfallback:")
    if r is not None and not degraded:
        try:
            await hold_service.verify_hold(r, body.hold_id, user.user_id, fid, seats)
        except ApiError:
            BOOKINGS.labels("hold_invalid").inc()
            raise
        except Exception:  # noqa: BLE001 Redis died mid-flight: DB guards still protect correctness
            degraded = True

    prices = await inv.db_inventory(pool, fid)
    by_class: dict[str, int] = {}
    for cl in classes.values():
        by_class[cl] = by_class.get(cl, 0) + 1
    total = round(sum(prices[cl]["price"] * n for cl, n in by_class.items()), 2)
    names = {p.seat_no: p.name for p in body.passengers}

    result = None
    for _attempt in range(6):
        pnr = new_pnr()
        try:
            result = await _txn(pool, user.user_id, fid, pnr, ikey, seats, classes, by_class, prices, names, total, fl)
            break
        except _Pnr:
            continue  # PNR/ticket collision on this shard: pick another
        except ApiError:
            BOOKINGS.labels("conflict").inc()
            if r is not None and not degraded:
                try:
                    await hold_service.release(app, body.hold_id, user.user_id)  # failed guard => release holds
                except Exception:  # noqa: BLE001
                    pass
            raise
    if result is None:
        raise ApiError(503, "DEGRADED", "could not allocate a PNR, retry")
    if not result.get("idempotent_replay"):
        await hold_service.finish_after_confirm(app, body.hold_id, fid, seats)
        BOOKINGS.labels("ok").inc()
    result["degraded"] = degraded
    return result


async def _txn(pool, user_id, fid, pnr, ikey, seats, classes, by_class, prices, names, total, fl):
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():  # single shard => single-node ACID
                row = await conn.fetchrow(
                    """INSERT INTO bookings (flight_id, pnr, user_id, status, total_price, idempotency_key)
                       VALUES ($1,$2,$3,'CONFIRMED',$4,$5) ON CONFLICT DO NOTHING RETURNING pnr""", fid, pnr, user_id, total, ikey)
                if row is None:
                    prior = await _replay(conn, fid, ikey)
                    if prior:
                        return prior
                    raise _Pnr()
                for sno in seats:  # sorted => consistent lock order => no deadlocks between buyers
                    tag = await conn.execute("INSERT INTO seats (flight_id, seat_no, fare_class, pnr, user_id) VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
                                             fid, sno, classes[sno], pnr, user_id)
                    if tag != "INSERT 0 1":
                        raise ApiError(409, "SEAT_CONFLICT", f"seat {sno} was just booked by someone else")
                for cl in sorted(by_class):
                    tag = await conn.execute("UPDATE seat_inventory SET available = available - $3 WHERE flight_id=$1 AND fare_class=$2 AND available >= $3",
                                             fid, cl, by_class[cl])
                    if tag != "UPDATE 1":
                        raise ApiError(409, "SEAT_UNAVAILABLE", f"no {cl.lower()} seats left")
                tag = await conn.execute("UPDATE flights SET seats_left = seats_left - $2 WHERE flight_id=$1 AND seats_left >= $2", fid, len(seats))
                if tag != "UPDATE 1":
                    raise ApiError(409, "SEAT_UNAVAILABLE", "flight is sold out")
                tickets = []
                for sno in seats:
                    tno = f"176{secrets.randbelow(10**10):010d}"
                    price = prices[classes[sno]]["price"]
                    await conn.execute("INSERT INTO tickets (flight_id, ticket_no, pnr, seat_no, fare_class, passenger_name, price) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                                       fid, tno, pnr, sno, classes[sno], names[sno], price)
                    tickets.append({"ticket_no": tno, "seat_no": sno, "fare_class": classes[sno], "passenger_name": names[sno], "price": price})
                payload = {"event": "BOOKING_CONFIRMED", "flight_id": fid, "pnr": pnr, "user_id": user_id, "seats": seats, "amount": total,
                           "by_class": by_class, "origin_id": fl["origin_id"], "dest_id": fl["dest_id"],
                           "ts": datetime.now(timezone.utc).isoformat()}
                await conn.execute("INSERT INTO outbox (flight_id, event_type, payload) VALUES ($1,'BOOKING_CONFIRMED',$2::jsonb)", fid, json.dumps(payload))
    except asyncpg.UniqueViolationError:
        raise _Pnr()
    return {"pnr": pnr, "flight_id": fid, "status": "CONFIRMED", "total_price": total, "idempotent_replay": False, "tickets": tickets}


async def cancel(app, user, flight_id: int, pnr: str) -> dict:
    st = app.state
    pool, r = st.pg_pool, st.redis
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    pnr = pnr.upper()
    async with pool.acquire() as conn:
        async with conn.transaction():
            b = await conn.fetchrow("UPDATE bookings SET status='CANCELLED' WHERE flight_id=$1 AND pnr=$2 AND user_id=$3 AND status='CONFIRMED' RETURNING total_price",
                                    flight_id, pnr, user.user_id)
            if b is None:
                raise ApiError(404, "NOT_FOUND", "booking not found or already cancelled")
            freed = await conn.fetch("DELETE FROM seats WHERE flight_id=$1 AND pnr=$2 RETURNING seat_no, fare_class", flight_id, pnr)
            by_class: dict[str, int] = {}
            for x in freed:
                by_class[x["fare_class"]] = by_class.get(x["fare_class"], 0) + 1
            for cl in sorted(by_class):
                await conn.execute("UPDATE seat_inventory SET available = available + $3 WHERE flight_id=$1 AND fare_class=$2", flight_id, cl, by_class[cl])
            await conn.execute("UPDATE flights SET seats_left = seats_left + $2 WHERE flight_id=$1", flight_id, len(freed))
            f = await conn.fetchrow("SELECT origin_id, dest_id FROM flights WHERE flight_id=$1", flight_id)
            payload = {"event": "BOOKING_CANCELLED", "flight_id": flight_id, "pnr": pnr, "user_id": user.user_id, "seats": [x["seat_no"] for x in freed],
                       "amount": -float(b["total_price"]), "by_class": by_class, "origin_id": f["origin_id"], "dest_id": f["dest_id"],
                       "ts": datetime.now(timezone.utc).isoformat()}
            await conn.execute("INSERT INTO outbox (flight_id, event_type, payload) VALUES ($1,'BOOKING_CANCELLED',$2::jsonb)", flight_id, json.dumps(payload))
    if r is not None:  # advisory counters follow the DB
        try:
            for cl, n in by_class.items():
                if await r.exists(inv.ckey(flight_id, cl)):
                    await r.incrby(inv.ckey(flight_id, cl), n)
        except Exception:  # noqa: BLE001
            pass
    BOOKINGS.labels("cancelled").inc()
    return {"pnr": pnr, "flight_id": flight_id, "status": "CANCELLED", "released_seats": [x["seat_no"] for x in freed]}


async def my_bookings(app, user_id: int) -> list[dict]:
    pool = app.state.pg_pool
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    rows = await pool.fetch(
        """SELECT b.flight_id, b.pnr, b.status, b.total_price, b.created_at, f.flight_no, f.departure_ts, ao.code AS origin, ad.code AS dest
           FROM bookings b JOIN flights f ON f.flight_id = b.flight_id
           JOIN airports ao ON ao.airport_id = f.origin_id JOIN airports ad ON ad.airport_id = f.dest_id
           WHERE b.user_id = $1 ORDER BY b.created_at DESC LIMIT 50""", user_id)
    if not rows:
        return []
    t = await pool.fetch("SELECT flight_id, pnr, ticket_no, seat_no, fare_class, passenger_name FROM tickets WHERE flight_id = ANY($1::bigint[]) AND pnr = ANY($2::text[])",
                         [x["flight_id"] for x in rows], [x["pnr"] for x in rows])
    by: dict[tuple, list] = {}
    for x in t:
        by.setdefault((x["flight_id"], x["pnr"]), []).append({k: x[k] for k in ("ticket_no", "seat_no", "fare_class", "passenger_name")})
    return [{"flight_id": x["flight_id"], "pnr": x["pnr"], "status": x["status"], "total_price": float(x["total_price"]),
             "created_at": x["created_at"].isoformat(), "flight_no": x["flight_no"], "departure_ts": x["departure_ts"].isoformat(),
             "origin": x["origin"], "dest": x["dest"], "tickets": by.get((x["flight_id"], x["pnr"]), [])} for x in rows]
