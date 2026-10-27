"""Route network + connecting paths. Neo4j when available; PostgreSQL `routes` fallback (direct + 1 stop) when it is down."""
import logging

log = logging.getLogger("ars")


async def network(app, limit: int = 250) -> dict:
    drv = app.state.neo4j
    if drv is not None:
        try:
            async with drv.session() as s:
                res = await s.run(
                    """MATCH (a:Airport)-[r:ROUTE]->(b:Airport) RETURN a.code AS o, a.city AS oc, b.code AS d, b.city AS dc, r.weekly AS w
                       ORDER BY w DESC LIMIT $n""", n=limit, timeout=4)
                rows = [x async for x in res]
            if rows:
                return _graph(rows, "neo4j")
        except Exception as e:  # noqa: BLE001
            log.warning("neo4j network failed: %s", e)
    pool = app.state.pg_pool
    if pool is None:
        return {"nodes": [], "edges": [], "source": "none", "degraded": True}
    rows = await pool.fetch(
        """SELECT ao.code AS o, ao.city AS oc, ad.code AS d, ad.city AS dc, count(*) AS w
           FROM (SELECT origin_id, dest_id FROM flights WHERE departure_ts BETWEEN now() AND now() + interval '1 day' LIMIT 200000) f
           JOIN airports ao ON ao.airport_id = f.origin_id JOIN airports ad ON ad.airport_id = f.dest_id
           GROUP BY 1,2,3,4 ORDER BY w DESC LIMIT $1""", limit)
    return _graph(rows, "postgres", degraded=drv is not None or bool(app.state.settings.neo4j_url))


def _graph(rows, source: str, degraded: bool = False) -> dict:
    nodes, edges = {}, []
    for r in rows:
        nodes[r["o"]] = {"id": r["o"], "city": r["oc"]}
        nodes[r["d"]] = {"id": r["d"], "city": r["dc"]}
        edges.append({"source": r["o"], "target": r["d"], "weekly_flights": int(r["w"])})
    return {"nodes": list(nodes.values()), "edges": edges, "source": source, "degraded": degraded}


async def paths(app, origin: str, dest: str, max_stops: int = 2) -> dict:
    origin, dest = origin.upper(), dest.upper()
    drv = app.state.neo4j
    if drv is not None:
        try:
            async with drv.session() as s:
                res = await s.run(
                    f"""MATCH p=(a:Airport {{code:$o}})-[:ROUTE*1..{int(max_stops) + 1}]->(b:Airport {{code:$d}})
                        RETURN [n IN nodes(p) | n.code] AS path ORDER BY length(p) LIMIT 8""", o=origin, d=dest, timeout=4)
                found = [x["path"] async for x in res]
            if found:
                return {"origin": origin, "destination": dest, "paths": found, "shortest": found[0], "source": "neo4j"}
        except Exception as e:  # noqa: BLE001
            log.warning("neo4j path failed: %s", e)
    pool = app.state.pg_pool
    if pool is None:
        return {"origin": origin, "destination": dest, "paths": [], "shortest": None, "source": "none", "degraded": True}
    direct = await pool.fetchval("""SELECT 1 FROM routes r JOIN airports a ON a.airport_id=r.origin_id JOIN airports b ON b.airport_id=r.dest_id
                                    WHERE a.code=$1 AND b.code=$2 LIMIT 1""", origin, dest)
    out = [[origin, dest]] if direct else []
    if max_stops >= 1:
        for r in await pool.fetch(
            """SELECT m.code AS via FROM routes r1 JOIN routes r2 ON r1.dest_id = r2.origin_id
               JOIN airports a ON a.airport_id=r1.origin_id JOIN airports m ON m.airport_id=r1.dest_id JOIN airports b ON b.airport_id=r2.dest_id
               WHERE a.code=$1 AND b.code=$2 LIMIT 8""", origin, dest):
            out.append([origin, r["via"], dest])
    return {"origin": origin, "destination": dest, "paths": out, "shortest": out[0] if out else None, "source": "postgres", "degraded": True}
