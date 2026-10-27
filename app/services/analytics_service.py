"""Admin dashboard (ClickHouse, eventually consistent) and cluster view (Citus metadata, Redis/Mongo/Neo4j/ClickHouse pings)."""
import asyncio
import json
import logging

import httpx

from app.db.http_clients import ch_query

log = logging.getLogger("ars")


async def dashboard(app) -> dict:
    s, pool, r = app.state.settings, app.state.pg_pool, app.state.redis
    out: dict = {"degraded": False}
    try:
        kpi, perday, top, hours = await asyncio.gather(
            ch_query(s, "SELECT countIf(event_type='BOOKED' AND ts >= toStartOfDay(now())) AS bookings_today, "
                        "sumIf(amount, ts >= toStartOfDay(now())) AS revenue_today FROM ars.booking_events"),
            ch_query(s, "SELECT toString(toDate(ts)) AS day, countIf(event_type='BOOKED') AS bookings, sum(amount) AS revenue "
                        "FROM ars.booking_events WHERE ts >= now() - INTERVAL 30 DAY GROUP BY day ORDER BY day"),
            ch_query(s, "SELECT origin_id, dest_id, count() AS bookings, sum(amount) AS revenue FROM ars.booking_events "
                        "WHERE event_type='BOOKED' GROUP BY origin_id, dest_id ORDER BY bookings DESC LIMIT 10"),
            ch_query(s, "SELECT toDayOfWeek(ts) AS dow, toHour(ts) AS hour, count() AS bookings FROM ars.booking_events "
                        "WHERE event_type='BOOKED' GROUP BY dow, hour ORDER BY dow, hour"))
        out.update(kpi=kpi[0] if kpi else {}, bookings_per_day=perday, hours=hours)
        codes = {}
        if pool is not None and top:
            ids = list({x["origin_id"] for x in top} | {x["dest_id"] for x in top})
            codes = {a["airport_id"]: a["code"] for a in await pool.fetch("SELECT airport_id, code FROM airports WHERE airport_id = ANY($1::int[])", ids)}
        out["top_routes"] = [{"route": f"{codes.get(int(x['origin_id']), x['origin_id'])}-{codes.get(int(x['dest_id']), x['dest_id'])}",
                              "bookings": int(x["bookings"]), "revenue": float(x["revenue"])} for x in top]
    except Exception as e:  # noqa: BLE001
        log.warning("clickhouse dashboard failed: %s", e)
        out.update(degraded=True, kpi={}, bookings_per_day=[], top_routes=[], hours=[])
    out["load_factor"] = await _load_factor(pool, r)
    out["error_rate"] = await _error_rate(s)
    return out


async def _load_factor(pool, r):
    if pool is None:
        return None
    try:
        if r is not None and (c := await r.get("stats:load_factor")):
            return float(c)
        v = await pool.fetchval(
            """SELECT round(100.0 * sum(si.total - si.available) / nullif(sum(si.total),0), 1) FROM seat_inventory si
               WHERE si.flight_id IN (SELECT flight_id FROM flights WHERE departure_ts BETWEEN now() AND now() + interval '2 hours' LIMIT 20000)""")
        v = float(v) if v is not None else None
        if r is not None and v is not None:
            await r.set("stats:load_factor", v, ex=60)
        return v
    except Exception:  # noqa: BLE001
        return None


async def _error_rate(s):
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            q = 'sum(rate(http_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(http_requests_total[1m])),1e-9)'
            j = (await c.get(f"{s.prometheus_url}/api/v1/query", params={"query": q})).json()
            res = j["data"]["result"]
            return round(float(res[0]["value"][1]) * 100, 2) if res else 0.0
    except Exception:  # noqa: BLE001
        return None


async def _ping(coro, timeout=2.0) -> str:
    try:
        await asyncio.wait_for(coro, timeout)
        return "up"
    except Exception:  # noqa: BLE001
        return "down"


async def cluster(app) -> dict:
    st = app.state
    s, pool = st.settings, st.pg_pool
    out: dict = {"services": {}, "citus": False, "workers": [], "shards": [], "replication_lag_s": {}}
    svc = out["services"]
    svc[s.node_name] = "up"
    svc["postgres"] = await _ping(pool.fetchval("SELECT 1")) if pool else "down"
    svc["redis"] = await _ping(st.redis.ping()) if st.redis else "disabled"
    svc["mongodb"] = await _ping(st.mongo.admin.command("ping")) if st.mongo is not None else "disabled"
    svc["neo4j"] = await _ping(st.neo4j.verify_connectivity()) if st.neo4j is not None else "disabled"
    if s.clickhouse_url:
        svc["clickhouse"] = await _ping(ch_query(s, "SELECT 1"))
    if pool is None:
        return out
    try:
        out["workers"] = [dict(r) for r in await pool.fetch(
            "SELECT nodename, nodeport, noderole, isactive, nodecluster FROM pg_dist_node ORDER BY nodeid")]
        out["citus"] = True
        out["shards"] = [{"node": r["nodename"], "shards": r["shards"], "size_bytes": int(r["size"] or 0), "est_rows": int(r["rows"] or 0)} for r in await pool.fetch(
            """SELECT s.nodename, count(*) AS shards, sum(s.shard_size) AS size,
                      (SELECT sum(greatest((x.result)::bigint,0)) FROM run_command_on_shards('flights', $$SELECT reltuples::bigint FROM pg_class WHERE oid='%s'::regclass$$) x
                       JOIN citus_shards s2 ON s2.shardid = x.shardid AND s2.table_name='flights'::regclass WHERE s2.nodename = s.nodename) AS rows
               FROM citus_shards s WHERE s.table_name='flights'::regclass GROUP BY s.nodename ORDER BY s.nodename""")]
        lag = await pool.fetch("""SELECT nodeid, result FROM run_command_on_workers(
              $$SELECT coalesce(max(extract(epoch from replay_lag)),0)::float8 FROM pg_stat_replication$$)""")
        out["replication_lag_s"] = {str(r["nodeid"]): float(r["result"] or 0) for r in lag}
    except Exception as e:  # noqa: BLE001  (plain PostgreSQL, e.g. in unit tests)
        log.info("cluster view: not a citus cluster (%s)", e)
    return out
