"""Seed ARS. Usage: python -m seed.seed [--scale 0.01] [--force]

SCALE=1 -> 50M flights, 150M seat_inventory, 2M users, ~20M bookings, ~35M tickets, 5k airports, 500 airlines, 200 aircraft.
Everything big is generated SERVER-SIDE with INSERT .. SELECT over generate_series (no Python row loop). On Citus the
flight-keyed INSERT..SELECTs are co-located, so they are pushed down and run in parallel on the workers.
Sold seats are consistent everywhere: seat_inventory.available = total - sold, seats rows exist for each sold seat, tickets match.
"""
import argparse
import asyncio
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import bcrypt
import httpx

REAL_AIRPORTS = [  # (code, name, city, country)
    ("KHI", "Jinnah International", "Karachi", "Pakistan"), ("LHR", "Heathrow", "London", "United Kingdom"),
    ("DXB", "Dubai International", "Dubai", "UAE"), ("JFK", "John F. Kennedy International", "New York", "USA"),
    ("ISB", "Islamabad International", "Islamabad", "Pakistan"), ("LHE", "Allama Iqbal International", "Lahore", "Pakistan"),
    ("DOH", "Hamad International", "Doha", "Qatar"), ("IST", "Istanbul Airport", "Istanbul", "Turkey"),
    ("SIN", "Changi", "Singapore", "Singapore"), ("BKK", "Suvarnabhumi", "Bangkok", "Thailand"),
    ("DEL", "Indira Gandhi International", "Delhi", "India"), ("BOM", "Chhatrapati Shivaji", "Mumbai", "India"),
    ("CDG", "Charles de Gaulle", "Paris", "France"), ("FRA", "Frankfurt Airport", "Frankfurt", "Germany"),
    ("AMS", "Schiphol", "Amsterdam", "Netherlands"), ("JED", "King Abdulaziz International", "Jeddah", "Saudi Arabia"),
    ("RUH", "King Khalid International", "Riyadh", "Saudi Arabia"), ("MAD", "Barajas", "Madrid", "Spain"),
    ("FCO", "Fiumicino", "Rome", "Italy"), ("LAX", "Los Angeles International", "Los Angeles", "USA"),
    ("ORD", "O'Hare", "Chicago", "USA"), ("YYZ", "Pearson", "Toronto", "Canada"),
    ("SYD", "Kingsford Smith", "Sydney", "Australia"), ("HKG", "Hong Kong International", "Hong Kong", "China"),
    ("NRT", "Narita", "Tokyo", "Japan"),
]
REAL_ROUTES = [("KHI", "LHR"), ("LHR", "KHI"), ("KHI", "DXB"), ("DXB", "KHI"), ("ISB", "DXB"), ("DXB", "ISB"), ("LHE", "DXB"),
               ("DXB", "LHE"), ("KHI", "JFK"), ("JFK", "KHI"), ("KHI", "IST"), ("IST", "KHI"), ("KHI", "DOH"), ("DOH", "KHI"),
               ("ISB", "LHR"), ("LHR", "ISB"), ("LHE", "LHR"), ("LHR", "LHE"), ("KHI", "JED"), ("JED", "KHI"),
               ("DXB", "LHR"), ("LHR", "DXB"), ("DEL", "BOM"), ("BOM", "DEL"), ("SIN", "BKK"), ("BKK", "SIN"),
               ("JFK", "LHR"), ("LHR", "JFK"), ("CDG", "FRA"), ("FRA", "CDG")]
N_AIRPORTS, N_AIRLINES, N_AIRCRAFT, N_ROUTES = 5000, 500, 200, 20000
DEMO_BASE = 900_000_000
PREFIX = "XZQWUVEGPT"  # first letters never used by REAL_AIRPORTS: generated codes cannot collide

# h(x): deterministic pseudo-random non-negative bigint
H = lambda x: f"abs(hashint8(({x})::int)::bigint)"  # noqa: E731


def layout(br: int, pr: int, er: int):
    """Seat numbers per class (3-3 layout A-F). Business rows first, then premium, then economy."""
    out, row = {}, 1
    for cls, rows in (("BUSINESS", br), ("PREMIUM", pr), ("ECONOMY", er)):
        out[cls] = [f"{r}{c}" for r in range(row, row + rows) for c in "ABCDEF"]
        row += rows
    return out


async def run(conn, sql, *a):
    await conn.execute(sql, *a)


async def main(scale: float, force: bool) -> None:
    dsn = dict(host=os.getenv("SEED_PG_HOST", "coordinator"), port=int(os.getenv("SEED_PG_PORT", "5432")),
               user=os.getenv("POSTGRES_USER", "ars"), password=os.getenv("POSTGRES_PASSWORD", ""),
               database=os.getenv("POSTGRES_DB", "ars"), command_timeout=None)
    conn = await asyncpg.connect(**dsn)
    existing = await conn.fetchval("SELECT count(*) FROM airports")
    if existing and not force:
        print("Already seeded (use --force to reseed).")
        return
    if existing:
        print("Truncating...")
        await conn.execute("TRUNCATE outbox, tickets, seats, bookings, seat_inventory, flights, email_registry, username_registry, users, routes, aircraft_types, airlines, airports")
    t0 = time.time()
    n_flights = max(1000, int(50_000_000 * scale))
    n_users = max(1000, int(2_000_000 * scale))
    batch = int(os.getenv("SEED_BATCH", "250000"))
    print(f"scale={scale}: flights={n_flights:,} users={n_users:,}")

    # ---- reference data
    real = REAL_AIRPORTS
    await conn.executemany("INSERT INTO airports VALUES ($1,$2,$3,$4,$5)",
                           [(i + 1, c, n, ci, co) for i, (c, n, ci, co) in enumerate(real)])
    await conn.execute(f"""
      INSERT INTO airports SELECT i, substr('{PREFIX}', 1 + (i/676)%10, 1) || chr(65+(i/26)%26) || chr(65+i%26),
             'Airport ' || i, 'City ' || i, 'Country ' || (i%90)
      FROM generate_series({len(real)+1}, {N_AIRPORTS}) i""")
    await conn.execute(f"""
      INSERT INTO airlines SELECT i, chr(65+((i-1)/26)%26) || chr(65+(i-1)%26), 'Airline ' || i FROM generate_series(1,{N_AIRLINES}) i""")
    await conn.execute(f"""
      INSERT INTO aircraft_types SELECT i, 'Aircraft-' || i, 1 + i%3, i%4, 12 + i%28 FROM generate_series(1,{N_AIRCRAFT}) i""")
    code2id = {c: i + 1 for i, (c, *_r) in enumerate(real)}
    rr = [(i + 1, code2id[a], code2id[b]) for i, (a, b) in enumerate(REAL_ROUTES)]
    await conn.executemany("INSERT INTO routes VALUES ($1,$2,$3)", rr)
    await conn.execute(f"""
      INSERT INTO routes SELECT r, 1 + r%{N_AIRPORTS},
             1 + ((r%{N_AIRPORTS}) + 1 + (r/{N_AIRPORTS})*100 + r%97) % {N_AIRPORTS}
      FROM generate_series({len(rr)+1}, {N_ROUTES}) r""")
    print(f"reference data ok ({time.time()-t0:.0f}s)")

    # ---- users (+ registries). Keep the named demo user in the user_1 slot.
    pw = bcrypt.hashpw(b"Passw0rd!", bcrypt.gensalt(rounds=10)).decode()
    for lo in range(2, n_users + 1, batch):
        hi = min(lo + batch - 1, n_users)
        await conn.execute("INSERT INTO users(user_id,username,email,password_hash,full_name) SELECT i,'user_'||i,'user_'||i||'@example.com',$1,'User '||i FROM generate_series($2::bigint,$3::bigint) i", pw, lo, hi)
        await conn.execute("INSERT INTO username_registry SELECT 'user_'||i, i FROM generate_series($1::bigint,$2::bigint) i", lo, hi)
        await conn.execute("INSERT INTO email_registry SELECT 'user_'||i||'@example.com', i FROM generate_series($1::bigint,$2::bigint) i", lo, hi)
    uid = 1
    demo = bcrypt.hashpw(b"hamza1234", bcrypt.gensalt(rounds=10)).decode()
    await conn.execute("INSERT INTO users(user_id,username,email,password_hash,full_name) VALUES ($1,'Hamza','hamza@example.com',$2,'Hamza')", uid, demo)
    await conn.execute("INSERT INTO username_registry VALUES ('Hamza',$1)", uid)
    await conn.execute("INSERT INTO email_registry VALUES ('hamza@example.com',$1)", uid)
    uid = n_users + 1
    adm = bcrypt.hashpw(b"admin1234", bcrypt.gensalt(rounds=10)).decode()
    await conn.execute("INSERT INTO users(user_id,username,email,password_hash,full_name,is_admin) VALUES ($1,'Admin_Hamza','admin.hamza@example.com',$2,'Hamza (Admin)',true)", uid, adm)
    await conn.execute("INSERT INTO username_registry VALUES ('Admin_Hamza',$1)", uid)
    await conn.execute("INSERT INTO email_registry VALUES ('admin.hamza@example.com',$1)", uid)
    await conn.execute("SELECT setval('user_id_seq', $1)", uid)
    print(f"users ok ({time.time()-t0:.0f}s)")

    # ---- flights and everything keyed by flight_id, in batches
    today = date.today()
    sold = "CASE WHEN i % 5 IN (0,1) THEN 1 + (i % 4 < 3)::int ELSE 0 END"
    for lo in range(1, n_flights + 1, batch):
        hi = min(lo + batch - 1, n_flights)
        # 1) flights (generate_series is coordinator-side; the rest below is pushed down to the workers)
        await conn.execute(f"""
        INSERT INTO flights
        SELECT i,
               (SELECT code FROM airlines WHERE airline_id = al) || (100 + {H('i+11')} % 9000),
               al, r.origin_id, r.dest_id, ac, dep, dep + make_interval(mins => dur), dur,
               (CASE WHEN {H('i+13')} % 10 < 7 THEN 0 WHEN {H('i+13')} % 10 < 9 THEN 1 ELSE 2 END)::smallint,
               pr,
               6 * (1 + ac % 3 + ac % 4 + 12 + ac % 28) - ({sold}),
               ARRAY[pr/2000.0, dur/1200.0, 0, extract(hour from dep)/24.0, extract(dow from dep)/7.0, al/500.0, ac/200.0, r.route_id/20000.0]::vector
        FROM (
          SELECT i,
                 1 + {H('i')} % {N_ROUTES} AS rid,
                 1 + {H('i+7')} % {N_AIRLINES} AS al,
                 1 + {H('i+9')} % {N_AIRCRAFT} AS ac,
                 (date '{today}' + ({H('i+3')} % 365)::int)::timestamptz + make_interval(hours => ({H('i+5')} % 24)::int, mins => (({H('i+6')} % 12)*5)::int) AS dep,
                 (60 + {H('i+1')} % 900)::int AS dur
          FROM generate_series({lo}::bigint, {hi}::bigint) i
        ) g
        JOIN routes r ON r.route_id = g.rid,
        LATERAL (SELECT round((40 + g.dur * 0.35 + {H('g.i+2')} % 200)::numeric, 2) AS pr) p""")
        # 2) inventory: 3 rows per flight
        await conn.execute(f"""
        INSERT INTO seat_inventory (flight_id, fare_class, total, available, price)
        SELECT f.flight_id, c.cls, c.tot, c.tot - CASE WHEN c.cls='ECONOMY' THEN s.sold ELSE 0 END, round(f.price * c.mult, 2)
        FROM flights f JOIN aircraft_types a ON a.aircraft_id = f.aircraft_id,
        LATERAL (SELECT CASE WHEN f.flight_id % 5 IN (0,1) THEN 1 + (f.flight_id % 4 < 3)::int ELSE 0 END AS sold) s,
        LATERAL (VALUES ('BUSINESS', a.business_rows*6, 3.2), ('PREMIUM', a.premium_rows*6, 1.8), ('ECONOMY', a.economy_rows*6, 1.0)) c(cls, tot, mult)
        WHERE f.flight_id BETWEEN {lo} AND {hi}""")
        # 3) bookings for 40% of flights (=> ~20M at scale 1), tickets (~35M) and the matching sold seats (economy)
        await conn.execute(f"""
        INSERT INTO bookings (flight_id, pnr, user_id, status, total_price, idempotency_key, created_at)
        SELECT f.flight_id, upper(substr(md5(f.flight_id::text),1,6)), 1 + (f.flight_id*7) % {n_users}, 'CONFIRMED',
               s.sold * f.price, 'seed-' || f.flight_id, now() - make_interval(secs => (f.flight_id % 5000000)::int)
        FROM flights f, LATERAL (SELECT CASE WHEN f.flight_id % 5 IN (0,1) THEN 1 + (f.flight_id % 4 < 3)::int ELSE 0 END AS sold) s
        WHERE f.flight_id BETWEEN {lo} AND {hi} AND s.sold > 0""")
        await conn.execute(f"""
        INSERT INTO seats (flight_id, seat_no, fare_class, pnr, user_id)
        SELECT f.flight_id, (a.business_rows + a.premium_rows + 1 + k/6)::text || chr(65 + k%6), 'ECONOMY',
               upper(substr(md5(f.flight_id::text),1,6)), 1 + (f.flight_id*7) % {n_users}
        FROM flights f JOIN aircraft_types a ON a.aircraft_id = f.aircraft_id,
        LATERAL (SELECT CASE WHEN f.flight_id % 5 IN (0,1) THEN 1 + (f.flight_id % 4 < 3)::int ELSE 0 END AS sold) s,
        LATERAL generate_series(0, s.sold - 1) k
        WHERE f.flight_id BETWEEN {lo} AND {hi} AND s.sold > 0""")
        await conn.execute(f"""
        INSERT INTO tickets (flight_id, ticket_no, pnr, seat_no, fare_class, passenger_name, price)
        SELECT f.flight_id, '176' || lpad(f.flight_id::text, 10, '0') || k, upper(substr(md5(f.flight_id::text),1,6)),
               (a.business_rows + a.premium_rows + 1 + k/6)::text || chr(65 + k%6), 'ECONOMY', 'Passenger ' || k, f.price
        FROM flights f JOIN aircraft_types a ON a.aircraft_id = f.aircraft_id,
        LATERAL (SELECT CASE WHEN f.flight_id % 5 IN (0,1) THEN 1 + (f.flight_id % 4 < 3)::int ELSE 0 END AS sold) s,
        LATERAL generate_series(0, s.sold - 1) k
        WHERE f.flight_id BETWEEN {lo} AND {hi} AND s.sold > 0""")
        done = hi / n_flights
        el = time.time() - t0
        print(f"flights {hi:,}/{n_flights:,} ({done:.0%}) elapsed {el/60:.1f} min, ETA {(el/done-el)/60:.1f} min", flush=True)

    # ---- demo flights with 1..5 economy seats left (KHI -> LHR, tomorrow). Aircraft 1: 2 bus rows, 1 prem row, 13 eco rows.
    tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    ac = await conn.fetchrow("SELECT * FROM aircraft_types WHERE aircraft_id=1")
    lay = layout(ac["business_rows"], ac["premium_rows"], ac["economy_rows"])
    for k in range(1, 6):
        fid = DEMO_BASE + k
        dep = tomorrow + timedelta(hours=6 + 2 * k)
        cap = sum(len(v) for v in lay.values())
        await conn.execute("INSERT INTO flights VALUES ($1,$2,1,1,2,1,$3,$4,420,0,999.00,$5,NULL)", fid, f"DM{100+k}", dep,
                           dep + timedelta(minutes=420), k)
        for cls, mult in (("BUSINESS", 3.2), ("PREMIUM", 1.8), ("ECONOMY", 1.0)):
            await conn.execute("INSERT INTO seat_inventory VALUES ($1,$2,$3,$4,$5)", fid, cls, len(lay[cls]),
                               k if cls == "ECONOMY" else 0, round(999.0 * mult, 2))
        sold_seats = [(s, c) for c, ss in lay.items() for s in ss]
        free = set(lay["ECONOMY"][:k])  # first k economy seats stay free
        await conn.executemany("INSERT INTO seats VALUES ($1,$2,$3,'DEMO00',1)", [(fid, s, c) for s, c in sold_seats if s not in free])
    # embeddings for demo flights match the generator's feature layout
    await conn.execute(f"UPDATE flights SET embedding = ARRAY[price/2000.0, duration_min/1200.0, 0, extract(hour from departure_ts)/24.0, extract(dow from departure_ts)/7.0, airline_id/500.0, aircraft_id/200.0, 0.0]::vector WHERE flight_id > {DEMO_BASE}")

    # ---- indexes AFTER the load
    print("building indexes (this is the slow part at full scale)...", flush=True)
    sql = (Path(__file__).resolve().parent.parent / "sql" / "003_indexes.sql").read_text()
    await conn.execute(sql)
    await conn.close()
    from seed.bloom import load_bloom
    await load_bloom(dsn)

    # ---- ClickHouse history for the dashboards
    ch = os.getenv("CLICKHOUSE_URL")
    if ch:
        try:
            await seed_clickhouse(ch, scale, dsn, rr)
        except Exception as e:  # noqa: BLE001
            print(f"ClickHouse seeding skipped: {e}")
    print(f"DONE in {(time.time()-t0)/60:.1f} min")


async def seed_clickhouse(url: str, scale: float, dsn: dict, real_routes) -> None:
    auth = (os.getenv("CLICKHOUSE_USER", "ars"), os.getenv("CLICKHOUSE_PASSWORD", ""))
    async with httpx.AsyncClient(timeout=3600, auth=auth) as c:
        for stmt in (Path(__file__).resolve().parent.parent / "sql" / "clickhouse_init.sql").read_text().split(";"):
            if stmt.strip():
                (await c.post(url, content=stmt)).raise_for_status()
        conn = await asyncpg.connect(**dsn)
        rows = await conn.fetch("SELECT route_id, origin_id, dest_id FROM routes")
        await conn.close()
        body = "\n".join(f'{{"route_id":{r[0]},"origin_id":{r[1]},"dest_id":{r[2]}}}' for r in rows)
        (await c.post(url, params={"query": "INSERT INTO ars.routes_dim FORMAT JSONEachRow"}, content=body)).raise_for_status()
        n = max(5000, int(20_000_000 * scale))
        q = f"""INSERT INTO ars.booking_events
        SELECT number, now() - toIntervalSecond(intDiv(cityHash64(number, 1) % 15552000, 1)) - toIntervalHour(0),
               'BOOKED', cityHash64(number, 2) % 50000000 + 1, hex(number % 16777216), cityHash64(number, 3) % 2000000 + 1,
               r.origin_id, r.dest_id, 1 + number % 4, (1 + number % 4) * (80 + cityHash64(number, 4) % 600)
        FROM numbers({n}) n
        INNER JOIN ars.routes_dim r ON r.route_id = 1 + toUInt32(pow(toFloat64(cityHash64(n.number, 5) % 1000000) / 1000000, 3) * 19999)"""
        (await c.post(url, content=q)).raise_for_status()
        print(f"ClickHouse: {n:,} historical booking events")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=float(os.getenv("SCALE", "0.01")))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.scale, a.force))
