"""Hold reconciler. Redis seat keys expire on their own TTL, but the per-class availability COUNTERS need repairing:
  1. expired holds: pop them from the `holds:expiry` ZSET (ZREM decides the single winner) and give the counters back
  2. drift repair: recompute counter = DB available - seats currently held, for flights that have counters
PostgreSQL stays the truth; this only keeps the advisory display fast and accurate."""
import asyncio
import json
import logging
import time

import redis.asyncio as aioredis

from workers.common import env, pg_pool

log = logging.getLogger("reconciler")
INTERVAL = float(env("RECONCILE_INTERVAL", "60"))
CLASSES = ("BUSINESS", "PREMIUM", "ECONOMY")


async def expire_holds(r) -> int:
    n = 0
    for hid in await r.zrangebyscore("holds:expiry", "-inf", time.time(), start=0, num=1000):
        if not await r.zrem("holds:expiry", hid):  # someone else (API release / other reconciler) already handled it
            continue
        raw = await r.get(f"holdmeta:{hid}")
        if raw:
            m = json.loads(raw)
            for c, k in m["by_class"].items():
                if await r.exists(f"avail:{m['flight_id']}:{c}"):
                    await r.incrby(f"avail:{m['flight_id']}:{c}", k)
            await r.srem(f"flightholds:{m['flight_id']}", hid)
            await r.delete(f"holdmeta:{hid}")
        n += 1
    return n


async def repair_drift(r, pool) -> int:
    fids: set[int] = set()
    async for key in r.scan_iter(match="avail:*", count=500):
        fids.add(int(key.split(":")[1]))
        if len(fids) >= 500:
            break
    if not fids:
        return 0
    rows = await pool.fetch("SELECT flight_id, fare_class, available FROM seat_inventory WHERE flight_id = ANY($1::bigint[])", list(fids))
    db = {(x["flight_id"], x["fare_class"]): x["available"] for x in rows}
    fixed = 0
    for fid in fids:
        held: dict[str, int] = {}
        for hid in await r.smembers(f"flightholds:{fid}"):
            raw = await r.get(f"holdmeta:{hid}")
            if raw:
                for c, k in json.loads(raw)["by_class"].items():
                    held[c] = held.get(c, 0) + k
        for c in CLASSES:
            if (fid, c) not in db:
                continue
            want = max(0, db[(fid, c)] - held.get(c, 0))
            cur = await r.get(f"avail:{fid}:{c}")
            if cur is not None and int(cur) != want:
                await r.set(f"avail:{fid}:{c}", want, keepttl=True)
                fixed += 1
    return fixed


async def main() -> None:
    pool = await pg_pool()
    r = aioredis.from_url(env("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    log.info("reconciler started (interval %.0fs)", INTERVAL)
    while True:
        try:
            e = await expire_holds(r)
            f = await repair_drift(r, pool)
            if e or f:
                log.info("expired holds=%d counters repaired=%d", e, f)
        except Exception as ex:  # noqa: BLE001
            log.warning("reconcile pass failed: %s", ex)
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
