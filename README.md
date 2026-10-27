# Airline Reservation System (ARS)

A distributed airline booking platform built for the Distributed Database Systems course: **PostgreSQL + Citus** (sharded truth), **Redis** (holds, cache, Bloom, rate limit),
**MongoDB** (audit/search events), **Neo4j** (route graph), **ClickHouse** (analytics), **pgvector** (similar flights), **FastAPI**, **React + TypeScript**, **Docker Compose**, **k6**.

## Quick start (lite stack, 16 GB RAM)
```bash
make up            # builds and starts ~20 containers, waits until the edge is healthy   (first build: 5-10 min)
make init-db       # registers Citus workers, creates and distributes the schema
make seed          # default SCALE=0.01 -> 500k flights, 20k users, 200k bookings (a few minutes)
make seed SCALE=1  # FULL: 50M flights, 150M seat_inventory, 2M users, 20M bookings, 35M tickets (hours; needs ~16 vCPU / 32 GB / 200 GB disk)
```
Open **http://localhost:8080** (app), **/docs** (OpenAPI), **http://localhost:3000** (Grafana), **http://localhost:9090** (Prometheus).
Logins: `Hamza` / `hamza1234`, admin: `Admin_Hamza` / `admin1234`. Demo flights **900000001..900000005** (Karachi to London) have 1 to 5 economy seats left.

Full HA stack (3 API nodes, 2 Nginx, streaming replicas for both workers and the coordinator, 3-node MongoDB replica set):
```bash
make up-full && make init-db-ha && make seed
```

## Commands
| Command | What it does |
|---|---|
| `make test-summary` | **One-command summary**: unit + race/API tests + k6 baseline + inventory invariants, prints PASS/FAIL table |
| `make test` | unit tests + automated race tests (inside the stack) |
| `make load` / `load-heavy` / `spike` / `soak` / `storm` | k6 baseline (500 users), 5,000 users, spike, soak, booking storm (+ invariant check) |
| `make chaos` | every chaos scenario the running stack supports |
| `make verify-distribution` | shards per worker, co-location proof, row estimates |
| `make verify-inventory` | must print 0 for negative inventory / double bookings / drift |
| `make health` | dependency report |
| `make frontend-dev` | Vite dev server on :5173 (proxy to :8080) |
| `make clean` | stop and delete all volumes |

## Troubleshooting
- **`make up` times out**: `make logs`; the usual cause is the first image build or low Docker memory (give Docker >= 12 GB).
- **`init-db` says worker not reachable**: wait for `docker compose ps` to show workers `healthy`, then rerun (idempotent).
- **Search returns nothing after `make up`**: you must run `make init-db` and `make seed` first.
- **Ports busy**: change `HTTP_PORT`, `PG_PUBLIC_PORT`, `GRAFANA_PORT` in `.env`.
- **k6 reports many 429**: expected under overload (load shedding). Failures are only 5xx / timeouts.
- **Admin simulation panel says controller unavailable**: `docker compose ps simctl`; it needs `/var/run/docker.sock` (Linux/macOS Docker Desktop).
- **Reset a corrupted topology after a failover demo**: `make clean && make up-full`.

## Documentation
- `docs/ARCHITECTURE_REPORT.md` - Mermaid diagram, sharding and consistency explanation, failure behaviour
- `docs/TRACEABILITY.md` - every requirement ID -> files -> verifying command
- `docs/TEST_EVIDENCE.md` - exact commands, expected output, and what was actually executed while building this
- `docs/DEMO_AND_VIVA.md` - 10 minute demo script and viva Q&A
- `MEMORY.md` - build progress, decisions, deviations, known issues
