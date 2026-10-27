# MEMORY.md: Project Memory (AI must read at the start and update at the end of every session)

## AI MANDATE
You must build the WHOLE project. This file is your persistent memory: it tells you what the project is, what has been decided, what is done, and what to do next. Update the "Progress" and "Decisions log" sections whenever you finish work, and print the updated file for the human to save.

## Project identity
- Name: Airline Reservation System (ARS)
- Course: Distributed Database Systems (university project)
- Team: max 3 members
- Goal: heavily distributed database system, 50M+ flight rows, web app plus always-on API
- Core DB: PostgreSQL (Citus sharding + streaming replicas)

## Course requirements (from the instructor)
1. Max 3 members
2. Heavily distributed database
3. Web or application
4. Search and sort, text and numeric search
5. API callable any time
6. Proper relational DB (PostgreSQL chosen)
7. No traffic may block or bring down the server (must be shown with a software simulation)
8. Scalable, distributed architecture

## Instructor guidelines (must be reflected in the design)
- High-volume, constantly changing, eventually consistent data -> document DB (MongoDB)
- Visualisation (graphs) -> graph DB (Neo4j)
- Similarity search -> vector DB (pgvector)
- Stats and dashboards -> columnar DB (ClickHouse)
- Booking systems: handle 2 parallel transactions on the same seat, the last available seat, caching, and showing remaining seats (ticket numbers or at least classes)
- Username existence check in constant time even with multiple master/coordinator nodes (same for similar cases)
- The database is the main thing: around 50 million rows

## Fixed decisions
| Topic | Decision |
|---|---|
| Domain | Airline reservation |
| Backend | Python 3.11, FastAPI, asyncpg |
| Frontend | React + Vite + Tailwind + TypeScript |
| Relational | PostgreSQL 16 + Citus, shard key `flight_id` |
| Cache/holds | Redis 7 |
| Document | MongoDB 7 replica set |
| Graph | Neo4j 5 |
| Columnar | ClickHouse |
| Vector | pgvector (HNSW) |
| Infra | Docker Compose, Nginx x2, PgBouncer |
| Load test | k6 |
| Monitoring | Prometheus + Grafana |
| Consistency | Strong for seats/bookings/uniqueness; eventual for the rest |
| Change propagation | Transactional outbox table + worker |

## Repository layout (create exactly this)
```
ars/
  docker-compose.yml
  docker-compose.lite.yml
  Makefile
  .env.example
  README.md
  sql/                 # 001_schema.sql, 002_citus_distribute.sql, 003_indexes.sql
  seed/                # seed.py
  app/                 # FastAPI (routers, services, db, schemas, core)
  workers/             # outbox_worker.py, hold_reconciler.py
  frontend/            # React app
  loadtest/            # k6 scripts, race_tests (pytest)
  chaos/               # failure scripts
  nginx/  pgbouncer/  prometheus/  grafana/
  docs/                # report, diagrams
```

## Build plan (do in order; tick when complete)
- [x] P1 Infrastructure: docker-compose (lite first), Nginx, PgBouncer, health checks, Makefile
- [x] P2 Database: schema, Citus distribution, indexes, replication
- [x] P3 Seeding: 50M+ rows, demo flights with 1 to 5 seats left
- [x] P4 Backend core: auth, O(1) username check, search and sort with cursor pagination
- [x] P5 Booking engine: Redis holds, single-shard confirm transaction, idempotency, cancellation, availability and seat map
- [x] P6 Race tests (all automated) passing
- [x] P7 Outbox worker + MongoDB + ClickHouse + Neo4j + pgvector integrations
- [x] P8 Frontend: search, seat map, checkout, bookings, graph, admin dashboard
- [x] P9 Load testing (k6), chaos scripts, Prometheus + Grafana
- [x] P10 Full docker-compose (HA), documentation, demo script, final verification

## Progress
(AI: update this after each phase)
- Current phase: ALL PHASES (P1-P10) WRITTEN; final step is the human running the Docker verification commands in docs/TEST_EVIDENCE.md
- Last completed: P10. Executed in the build sandbox (plain PostgreSQL 16 + pgvector + Redis, 1 CPU core, no Docker/Citus): 36 pytest tests pass (race + API + unit), inventory invariants all 0, seed consistency checks pass at SCALE=0.004, Redis-outage degradation verified, frontend type-checks and builds.
- Known issues / NOT verified (need your Docker host): all docker-compose files and Dockerfiles; Citus distribution (sql/002) and shard behaviour; seed at SCALE=1 (hours, runtime and ClickHouse insert untested); Neo4j loader; ClickHouse queries; simctl sidecar; k6 numbers for N-2/N-3/N-4/N-5; failover scripts (N-8). Replica entrypoint, `citus_add_secondary_node` and the DNS-alias promotion trick are written from documentation and untested.