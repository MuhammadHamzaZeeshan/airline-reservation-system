"""Similar flights via pgvector cosine distance. Candidates are first restricted to the same route and a +-3 day window with
ordinary B-tree filters (so the search stays exact and fast), then ranked by embedding distance."""
from app.core.errors import ApiError


async def similar(app, flight_id: int, limit: int = 8) -> dict:
    pool = app.state.pg_pool
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    f = await pool.fetchrow("SELECT origin_id, dest_id, departure_ts, embedding::text AS emb FROM flights WHERE flight_id=$1", flight_id)
    if f is None:
        raise ApiError(404, "NOT_FOUND", "flight not found")
    if f["emb"] is None:
        return {"flight_id": flight_id, "items": []}
    rows = await pool.fetch(
        """SELECT f.flight_id, f.flight_no, al.name AS airline_name, ao.code AS origin_code, ad.code AS dest_code,
                  f.departure_ts, f.duration_min, f.stops, f.price, f.seats_left, (f.embedding <=> $5::text::vector) AS distance
           FROM flights f JOIN airlines al ON al.airline_id=f.airline_id
           JOIN airports ao ON ao.airport_id=f.origin_id JOIN airports ad ON ad.airport_id=f.dest_id
           WHERE f.origin_id=$1 AND f.dest_id=$2 AND f.departure_ts BETWEEN $3::timestamptz - interval '3 days' AND $3::timestamptz + interval '3 days'
             AND f.flight_id <> $4 AND f.seats_left > 0 AND f.embedding IS NOT NULL
           ORDER BY distance LIMIT $6""", f["origin_id"], f["dest_id"], f["departure_ts"], flight_id, f["emb"], limit)
    return {"flight_id": flight_id, "items": [{**dict(r), "price": float(r["price"]), "distance": float(r["distance"]),
                                               "departure_ts": r["departure_ts"].isoformat()} for r in rows]}
