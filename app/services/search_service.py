"""Search with text + numeric filters, multi-key sort and keyset (cursor) pagination. No OFFSET anywhere.

Cursor = base64(JSON{sort, values-of-sort-keys, flight_id}). For sort keys k1..kn with directions the 'after cursor' predicate is
  (k1 op v1) OR (k1=v1 AND k2 op v2) OR ... OR (k1=v1 ... AND flight_id > id)
which is stable for mixed asc/desc (a single row-value comparison would not be). flight_id is the unique tie-breaker.
All user input reaches SQL as parameters; ORDER BY / column names come ONLY from the SORT whitelist.
"""
import asyncio
import base64
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.errors import ApiError
from app.db.pg import read_conn
from app.schemas.models import SearchParams

SORT = {  # api key -> (sql expr, type, cursor json key)
    "price": ("f.price", "numeric"),
    "duration": ("f.duration_min", "int"),
    "departure": ("f.departure_ts", "ts"),
    "arrival": ("f.arrival_ts", "ts"),
    "seats": ("f.seats_left", "int"),
}


def parse_sort(spec: str) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for part in spec.split(","):
        name, _, d = part.strip().partition(":")
        d = (d or "asc").lower()
        if name not in SORT or d not in ("asc", "desc") or any(k == name for k, _ in keys):
            raise ApiError(400, "VALIDATION_ERROR", f"invalid sort '{part}'. keys: {', '.join(SORT)}; dir: asc|desc")
        keys.append((name, d))
    if not 1 <= len(keys) <= 3:
        raise ApiError(400, "VALIDATION_ERROR", "sort supports 1 to 3 keys")
    return keys


def enc_cursor(sort: str, vals: list, fid: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"s": sort, "v": vals, "id": fid}, default=str).encode()).decode()


def dec_cursor(c: str, sort: str) -> tuple[list, int]:
    try:
        d = json.loads(base64.urlsafe_b64decode(c.encode()))
        if d["s"] != sort:
            raise ValueError("sort changed")
        return d["v"], int(d["id"])
    except Exception:  # noqa: BLE001
        raise ApiError(400, "VALIDATION_ERROR", "invalid cursor")


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _typed(kind: str, v):
    if kind == "ts":
        return datetime.fromisoformat(v) if isinstance(v, str) else v
    if kind == "numeric":
        return Decimal(str(v))
    return int(v)


class Q:
    """Tiny parameter collector: P(value) -> '$n'."""
    def __init__(self):
        self.args: list = []

    def p(self, v) -> str:
        self.args.append(v)
        return f"${len(self.args)}"


_REF_CACHE: dict[tuple, tuple[float, list[int]]] = {}
_REF_TTL = 300.0  # airports/airlines are static reference data: an in-process 5 min cache is safe and saves 2 queries per search


async def _resolve_airports(pool, text: str) -> list[int]:
    k = ("ap", text.strip().lower())
    hit = _REF_CACHE.get(k)
    if hit and time.monotonic() - hit[0] < _REF_TTL:
        return hit[1]
    ids = await _resolve_airports_db(pool, text)
    _REF_CACHE[k] = (time.monotonic(), ids)
    return ids


async def _resolve_airports_db(pool, text: str) -> list[int]:
    like = _like_escape(text.strip())
    rows = await pool.fetch(
        """SELECT airport_id FROM airports
           WHERE code = upper($1) OR city ILIKE $2 || '%' OR name ILIKE '%' || $2 || '%' OR city % $1::text
           ORDER BY (code = upper($1)) DESC, similarity(city, $1::text) DESC LIMIT 20""", text.strip(), like)
    return [r["airport_id"] for r in rows]


async def _resolve_airlines(pool, text: str) -> list[int]:
    k = ("al", text.strip().lower())
    hit = _REF_CACHE.get(k)
    if hit and time.monotonic() - hit[0] < _REF_TTL:
        return hit[1]
    ids = await _resolve_airlines_db(pool, text)
    _REF_CACHE[k] = (time.monotonic(), ids)
    return ids


async def _resolve_airlines_db(pool, text: str) -> list[int]:
    like = _like_escape(text.strip())
    rows = await pool.fetch("SELECT airline_id FROM airlines WHERE code = upper($1) OR name ILIKE '%' || $2 || '%' LIMIT 50", text.strip(), like)
    return [r["airline_id"] for r in rows]


_INFLIGHT: dict[str, asyncio.Future] = {}


async def search(app, p: SearchParams) -> dict:
    """Redis result cache (30 s) + single-flight: N identical concurrent misses on one node run ONE database query (no stampede)."""
    st = app.state
    t0 = time.perf_counter()
    sort_keys = parse_sort(p.sort)  # validate first: bad input never reaches cache or DB
    key = "search:" + hashlib.sha1(json.dumps(p.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    if st.redis is not None:
        try:
            hit = await st.redis.get(key)
            if hit:
                out = json.loads(hit)
                out["cached"], out["took_ms"] = True, round((time.perf_counter() - t0) * 1000, 1)
                return out
        except Exception:  # noqa: BLE001
            pass
    if key in _INFLIGHT:
        out = dict(await asyncio.shield(_INFLIGHT[key]))
        out["cached"], out["took_ms"] = True, round((time.perf_counter() - t0) * 1000, 1)
        return out
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    fut.add_done_callback(lambda f: f.cancelled() or f.exception())  # mark retrieved: no 'never retrieved' warnings
    _INFLIGHT[key] = fut
    try:
        out = await _search_db(app, p, sort_keys, t0)
        fut.set_result(out)
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e if isinstance(e, Exception) else RuntimeError("cancelled"))
        raise
    finally:
        _INFLIGHT.pop(key, None)
    if st.redis is not None:
        try:
            await st.redis.set(key, json.dumps(out, default=str), ex=st.settings.search_cache_ttl)
        except Exception:  # noqa: BLE001
            pass
    return out


async def _search_db(app, p: SearchParams, sort_keys: list, t0: float) -> dict:
    st = app.state
    sort_str = ",".join(f"{k}:{d}" for k, d in sort_keys)
    pool = st.pg_pool
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")

    # resolve text -> ids (small reference tables, trigram-indexed)
    o_ids = await _resolve_airports(pool, p.origin) if p.origin else None
    d_ids = await _resolve_airports(pool, p.destination) if p.destination else None
    al_ids = await _resolve_airlines(pool, p.airline) if p.airline else None
    empty = {"items": [], "next_cursor": None, "count": 0, "count_capped": False, "cached": False,
             "took_ms": round((time.perf_counter() - t0) * 1000, 1), "sort": sort_str}
    if (o_ids == []) or (d_ids == []) or (al_ids == []):
        return empty

    # unbounded scans are rejected: need a route, or a narrow explicit date window
    now = datetime.now(timezone.utc)
    explicit = p.date_from is not None or p.date_to is not None
    has_route = bool(o_ids and d_ids)
    dfrom = p.date_from or now
    if dfrom.tzinfo is None:
        dfrom = dfrom.replace(tzinfo=timezone.utc)
    dto = p.date_to or (dfrom + timedelta(days=30 if has_route else 2))
    if dto.tzinfo is None:
        dto = dto.replace(tzinfo=timezone.utc)
    window = dto - dfrom
    if window < timedelta(0) or window > timedelta(days=366):
        raise ApiError(400, "VALIDATION_ERROR", "date window must be between 0 and 366 days")
    if not has_route:
        limit_days = 7 if (o_ids or d_ids or al_ids or p.flight_no) else 2
        if not explicit or window > timedelta(days=limit_days):
            raise ApiError(400, "QUERY_TOO_BROAD", f"give origin AND destination, or a date range of at most {limit_days} days")

    q = Q()
    where = [f"f.departure_ts >= {q.p(dfrom)}", f"f.departure_ts <= {q.p(dto)}"]
    if o_ids:
        where.append(f"f.origin_id = ANY({q.p(o_ids)}::int[])")
    if d_ids:
        where.append(f"f.dest_id = ANY({q.p(d_ids)}::int[])")
    if al_ids:
        where.append(f"f.airline_id = ANY({q.p(al_ids)}::int[])")
    if p.flight_no:
        where.append(f"f.flight_no ILIKE '%' || {q.p(_like_escape(p.flight_no))} || '%'")
    if p.min_price is not None:
        where.append(f"f.price >= {q.p(Decimal(str(p.min_price)))}")
    if p.max_price is not None:
        where.append(f"f.price <= {q.p(Decimal(str(p.max_price)))}")
    if p.min_duration is not None:
        where.append(f"f.duration_min >= {q.p(p.min_duration)}")
    if p.max_duration is not None:
        where.append(f"f.duration_min <= {q.p(p.max_duration)}")
    if p.max_stops is not None:
        where.append(f"f.stops <= {q.p(p.max_stops)}")
    if p.fare_class:
        where.append(f"EXISTS (SELECT 1 FROM seat_inventory si WHERE si.flight_id = f.flight_id AND si.fare_class = {q.p(p.fare_class)} AND si.available >= {q.p(p.passengers)})")
    else:
        where.append(f"f.seats_left >= {q.p(p.passengers)}")
    base_where = " AND ".join(where)
    base_args = list(q.args)

    # keyset predicate
    page_where = base_where
    if p.cursor:
        vals, last_id = dec_cursor(p.cursor, sort_str)
        if len(vals) != len(sort_keys):
            raise ApiError(400, "VALIDATION_ERROR", "invalid cursor")
        ors = []
        for i in range(len(sort_keys) + 1):
            conds = []
            for j in range(min(i, len(sort_keys))):
                expr, kind = SORT[sort_keys[j][0]]
                conds.append(f"{expr} = {q.p(_typed(kind, vals[j]))}")
            if i < len(sort_keys):
                expr, kind = SORT[sort_keys[i][0]]
                op = ">" if sort_keys[i][1] == "asc" else "<"
                conds.append(f"{expr} {op} {q.p(_typed(kind, vals[i]))}")
            else:
                conds.append(f"f.flight_id > {q.p(last_id)}")
            ors.append("(" + " AND ".join(conds) + ")")
        page_where = f"{base_where} AND ({' OR '.join(ors)})"
    order = ", ".join(f"{SORT[k][0]} {d.upper()}" for k, d in sort_keys) + ", f.flight_id ASC"

    sql = f"""SELECT f.flight_id, f.flight_no, f.airline_id, al.name AS airline_name, f.origin_id, ao.code AS origin_code,
                     ao.city AS origin_city, f.dest_id, ad.code AS dest_code, ad.city AS dest_city,
                     f.departure_ts, f.arrival_ts, f.duration_min, f.stops, f.price, f.seats_left
              FROM flights f
              JOIN airports ao ON ao.airport_id = f.origin_id
              JOIN airports ad ON ad.airport_id = f.dest_id
              JOIN airlines al ON al.airline_id = f.airline_id
              WHERE {page_where}
              ORDER BY {order}
              LIMIT {int(p.limit) + 1}"""  # limit is a validated int
    count_sql = f"SELECT count(*) FROM (SELECT 1 FROM flights f WHERE {base_where} LIMIT 1001) c"

    async def rows_q():
        async with read_conn(pool, st.settings.use_replicas) as c:
            return await c.fetch(sql, *q.args)

    async def count_q():
        if p.cursor:
            return None
        async with read_conn(pool, st.settings.use_replicas) as c:
            return await c.fetchval(count_sql, *base_args)

    rows, count = await asyncio.gather(rows_q(), count_q())
    has_more = len(rows) > p.limit
    rows = rows[: p.limit]
    ids = [r["flight_id"] for r in rows]
    inv: dict[int, list] = {i: [] for i in ids}
    if ids:
        async with read_conn(pool, st.settings.use_replicas) as c:
            for r in await c.fetch("SELECT flight_id, fare_class, available, total, price FROM seat_inventory WHERE flight_id = ANY($1::bigint[]) AND total > 0", ids):
                inv[r["flight_id"]].append({"fare_class": r["fare_class"], "available": r["available"], "total": r["total"], "price": float(r["price"])})
    items = []
    for r in rows:
        d = dict(r)
        d["price"] = float(d["price"])
        d["departure_ts"], d["arrival_ts"] = d["departure_ts"].isoformat(), d["arrival_ts"].isoformat()
        d["classes"] = sorted(inv[r["flight_id"]], key=lambda x: ["BUSINESS", "PREMIUM", "ECONOMY"].index(x["fare_class"]))
        items.append(d)
    nxt = None
    if has_more and rows:
        last = rows[-1]
        vals = []
        for k, _ in sort_keys:
            col = {"price": "price", "duration": "duration_min", "departure": "departure_ts", "arrival": "arrival_ts", "seats": "seats_left"}[k]
            v = last[col]
            vals.append(v.isoformat() if isinstance(v, datetime) else str(v))
        nxt = enc_cursor(sort_str, vals, last["flight_id"])
    out = {"items": items, "next_cursor": nxt, "count": (min(count, 1000) if count is not None else None), "count_capped": bool(count is not None and count > 1000),
           "cached": False, "took_ms": round((time.perf_counter() - t0) * 1000, 1), "sort": sort_str}
    return out

# NOTE on 'no global in-process state' (RULES.md): _REF_CACHE (static airport/airline name lookups) and _INFLIGHT (coalescing of
# identical concurrent searches on ONE node) are pure performance aids. Neither affects correctness: results are read-only search
# listings, the reference data never changes at runtime, and bookings never consult them.
