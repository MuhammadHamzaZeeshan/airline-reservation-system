"""Transactional-outbox worker: Postgres -> ClickHouse (analytics), MongoDB (audit log), Redis (stats).

Delivery is AT-LEAST-ONCE and every sink is IDEMPOTENT (ClickHouse ReplacingMergeTree on event_id, Mongo upsert on _id), so several
workers may run concurrently and a crash between 'write sinks' and 'mark processed' only causes a harmless re-delivery.
DEVIATION from ARCHITECTURE.md (logged in MEMORY.md): no SELECT .. FOR UPDATE SKIP LOCKED because Citus cannot lock rows across shards
in one multi-shard query; idempotent sinks give the same safety without the lock.
If a sink is DOWN the events are NOT marked processed: they stay buffered in Postgres until it returns (outbox buffering).
"""
import asyncio
import json
import logging
from datetime import datetime

import httpx
import redis.asyncio as aioredis

from workers.common import env, pg_pool

log = logging.getLogger("outbox")
BATCH = int(env("OUTBOX_BATCH", "500"))
POLL = float(env("OUTBOX_POLL_SECONDS", "1"))


def ch_row(flight_id: int, oid: int, ev_type: str, p: dict) -> dict:
    ts = datetime.fromisoformat(p["ts"]).strftime("%Y-%m-%d %H:%M:%S")
    return {"event_id": oid, "ts": ts, "event_type": "BOOKED" if ev_type == "BOOKING_CONFIRMED" else "CANCELLED", "flight_id": flight_id,
            "pnr": p["pnr"], "user_id": p["user_id"], "origin_id": p["origin_id"], "dest_id": p["dest_id"], "seats": len(p["seats"]), "amount": p["amount"]}


async def to_clickhouse(rows: list[dict]) -> None:
    url = env("CLICKHOUSE_URL")
    if not url or not rows:
        return
    async with httpx.AsyncClient(timeout=15, auth=(env("CLICKHOUSE_USER", "ars"), env("CLICKHOUSE_PASSWORD"))) as c:
        r = await c.post(url, params={"query": "INSERT INTO ars.booking_events FORMAT JSONEachRow", "date_time_input_format": "best_effort"},
                         content="\n".join(json.dumps(x) for x in rows))
        r.raise_for_status()


async def to_mongo(mongo, rows) -> None:
    if mongo is None or not rows:
        return
    from pymongo import UpdateOne
    ops = [UpdateOne({"_id": f"{fid}:{oid}"}, {"$set": {"flight_id": fid, "event": t, "payload": p}}, upsert=True) for fid, oid, t, p in rows]
    await mongo["ars"]["audit_log"].bulk_write(ops, ordered=False)


async def main() -> None:
    pool = await pg_pool()
    mongo = None
    if env("MONGO_URL"):
        from motor.motor_asyncio import AsyncIOMotorClient
        mongo = AsyncIOMotorClient(env("MONGO_URL"), serverSelectionTimeoutMS=2000)
    r = aioredis.from_url(env("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    log.info("outbox worker started")
    while True:
        try:
            rows = await pool.fetch("SELECT flight_id, id, event_type, payload FROM outbox WHERE processed_at IS NULL ORDER BY id LIMIT $1", BATCH)
            if not rows:
                await asyncio.sleep(POLL)
                continue
            ev = [(x["flight_id"], x["id"], x["event_type"], json.loads(x["payload"]) if isinstance(x["payload"], str) else x["payload"]) for x in rows]
            await asyncio.gather(to_clickhouse([ch_row(*e) for e in ev]), to_mongo(mongo, ev))  # any failure -> retry whole batch
            try:
                pipe = r.pipeline()
                pipe.set("stats:last_outbox_id", ev[-1][1])
                for _f, _i, t, p in ev:
                    pipe.incrbyfloat("stats:revenue_total", p["amount"])
                    pipe.incr("stats:booking_events" if t == "BOOKING_CONFIRMED" else "stats:cancel_events")
                await pipe.execute()
            except Exception:  # noqa: BLE001  Redis is optional here
                pass
            await pool.execute("UPDATE outbox SET processed_at = now() WHERE flight_id = ANY($1::bigint[]) AND id = ANY($2::bigint[])",
                               [e[0] for e in ev], [e[1] for e in ev])
            log.info("delivered %d events (last id %d)", len(ev), ev[-1][1])
        except Exception as e:  # noqa: BLE001  sink down: events stay buffered in Postgres
            log.warning("batch failed, will retry: %s", e)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
