"""Rebuilds the Neo4j route network from PostgreSQL (eventually consistent, refreshed hourly). Edge weight = flights in the next 7 days."""
import asyncio
import logging

from neo4j import AsyncGraphDatabase

from workers.common import env, pg_pool

log = logging.getLogger("graph")
EVERY = float(env("GRAPH_REFRESH_SECONDS", "3600"))


async def load(pool, drv) -> int:
    rows = await pool.fetch(
        """SELECT ao.code AS o, ao.city AS oc, ad.code AS d, ad.city AS dc, count(*) AS w
           FROM flights f JOIN airports ao ON ao.airport_id = f.origin_id JOIN airports ad ON ad.airport_id = f.dest_id
           WHERE f.departure_ts BETWEEN now() AND now() + interval '7 days' GROUP BY 1,2,3,4""")
    if not rows:  # nothing in the next 7 days (tiny dataset): fall back to the static route table
        rows = await pool.fetch("""SELECT ao.code AS o, ao.city AS oc, ad.code AS d, ad.city AS dc, 1 AS w FROM routes r
                                   JOIN airports ao ON ao.airport_id = r.origin_id JOIN airports ad ON ad.airport_id = r.dest_id""")
    data = [dict(r) for r in rows]
    async with drv.session() as s:
        await s.run("CREATE CONSTRAINT airport_code IF NOT EXISTS FOR (a:Airport) REQUIRE a.code IS UNIQUE")
        for i in range(0, len(data), 2000):
            await s.run("""UNWIND $rows AS r
                           MERGE (a:Airport {code: r.o}) SET a.city = r.oc
                           MERGE (b:Airport {code: r.d}) SET b.city = r.dc
                           MERGE (a)-[e:ROUTE]->(b) SET e.weekly = r.w""", rows=data[i:i + 2000])
    return len(data)


async def main() -> None:
    pool = await pg_pool()
    drv = AsyncGraphDatabase.driver(env("NEO4J_URL", "bolt://neo4j:7687"), auth=(env("NEO4J_USER", "neo4j"), env("NEO4J_PASSWORD")))
    while True:
        try:
            n = await load(pool, drv)
            log.info("route graph refreshed: %d edges", n)
            await asyncio.sleep(EVERY)
        except Exception as e:  # noqa: BLE001  Neo4j or Postgres not ready: retry soon
            log.warning("graph refresh failed: %s", e)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
