# Requirements traceability (ID -> files -> verifying command)

"Executed here" = run in the build sandbox (single CPU core, plain PostgreSQL 16 + Redis, no Docker). "Run on your machine" = needs the Docker stack; commands are given.

| ID | Implementation | Verification |
|---|---|---|
| C-1 | team of up to 3 (organisational) | n/a |
| C-2, C-8 | `docker-compose.lite.yml`, `docker-compose.yml`, `sql/002_citus_distribute.sql`, `nginx/` | `make verify-distribution` (run on your machine) |
| C-3 | `frontend/` | `cd frontend && npm run build` (executed here: type-check + build OK) |
| C-4 | `app/services/search_service.py`, `app/routers/flights.py` | `test_search_text_and_numeric`, `test_cursor_pagination_multikey` (executed here) |
| C-5 | stateless API behind Nginx, `/v1` | `make chaos` (kill_api_node); `test_health` |
| C-6 | `sql/001_schema.sql` (PostgreSQL 16 + Citus) | schema applied and seeded (executed here) |
| C-7 | `nginx/nginx.conf` limits, `app/core/ratelimit.py`, bounded pool, `loadtest/k6/heavy.js` | `make load-heavy` (run on your machine) |
| C-9 | `seed/seed.py` | `make seed SCALE=1`; consistency queries executed here at SCALE=0.004 |
| C-10 | Redis, MongoDB, Neo4j, ClickHouse, pgvector services and routers | `make chaos` (kill_stores); `test_routes_and_path`, `test_similar_flights` |
| C-11 | `app/services/booking_service.py`, `hold_service.py` | `loadtest/race_tests/test_races.py` (executed here, 12 tests) |
| C-12 | `app/services/inventory.py` (counters + seat map), `hold_service.py` | `test_demo_flights_availability_and_seatmap`, `test_hold_expiry` (executed here) |
| C-13 | `app/services/user_service.py`, `seed/bloom.py`, `sql/002` (registry distributed by value) | `test_duplicate_registration_race`, `test_duplicate_email_race`, `test_username_availability` (executed here) |
| F-1 | `app/routers/auth.py`, `app/core/security.py` | `test_auth_flow` |
| F-2 | `app/routers/users.py` | `test_username_availability` |
| F-3 | `search_service.py` (trigram + ILIKE on airports, airlines, flight_no) | `test_search_text_and_numeric` |
| F-4 | `search_service.py` (price, duration, date range, stops, seats) | `test_search_text_and_numeric` |
| F-5 | `parse_sort` whitelist, multi-key | `test_cursor_pagination_multikey`, `test_invalid_sort_is_rejected_not_injected` |
| F-6 | keyset cursor in `search_service.py` | `test_cursor_pagination_multikey` |
| F-7 | `inventory.availability` | `test_demo_flights_availability_and_seatmap` |
| F-8 | `inventory.seat_map`, `frontend/src/components/SeatMap.tsx` | same test |
| F-9 | `hold_service.py`, `workers/hold_reconciler.py` | `test_hold_expiry`, `test_hold_release_frees_seat`, `test_hold_validation` |
| F-10 | `booking_service.confirm` | `test_idempotent_retry`, `test_booking_requires_idempotency_key` |
| F-11 | `booking_service.cancel` | `test_cancel_releases_seat` |
| F-12 | `booking_service.my_bookings` | `test_my_bookings_lists_new_booking` |
| F-13 | `recommendation_service.py`, HNSW in `sql/003_indexes.sql` | `test_similar_flights` |
| F-14 | `graph_service.py`, `workers/graph_loader.py`, `Network.tsx` | `test_routes_and_path` (PostgreSQL fallback executed here; Neo4j path run on your machine) |
| F-15 | `analytics_service.dashboard`, `workers/outbox_worker.py`, `Admin.tsx` | `test_admin_endpoints` (degraded mode executed here); full data run on your machine |
| F-16 | `analytics_service.cluster`, `Admin.tsx` | `test_admin_endpoints`; Citus data on your machine |
| F-17 | `docker/simctl/simctl.py`, `app/routers/admin.py`, `Admin.tsx` | `test_admin_endpoints` (whitelist); panel buttons on your machine |
| F-18 | `/v1/*`, FastAPI `/docs` | open `/docs` |
| N-1 | Nginx upstreams, stateless API, graceful degradation | `make chaos` |
| N-2 | indexes in `sql/003`, cache + single-flight, `loadtest/k6/baseline.js` | `make load` (run on your machine at SCALE=1; not provable on a 1-core sandbox) |
| N-3 | `loadtest/k6/heavy.js`, 429 shedding | `make load-heavy` (run on your machine) |
| N-4 | single-shard transaction | `make storm` (k6 booking latency, run on your machine) |
| N-5 | 2 nodes x 2 workers, PgBouncer, cache | `make load-heavy` (check Grafana req/s on your machine) |
| N-6 | see consistency model in `ARCHITECTURE_REPORT.md` | design |
| N-7 | race tests + `sql/verify_inventory.sql` | `make test-race && make verify-inventory` (executed here: 0 violations) |
| N-8 | `chaos/failover_worker.sh`, sync replication in `scripts/init_db.sh` | `make up-full && make init-db-ha && ./chaos/failover_worker.sh` (run on your machine) |
| N-9 | bcrypt, JWT, parameterised SQL, validation, rate limits | `test_validation_errors`, `test_invalid_sort_is_rejected_not_injected` |
| N-10 | `/metrics`, `grafana/dashboards/ars.json`, JSON logs, `/health` | open Grafana :3000 |
| N-11 | `Makefile`, `scripts/init_db.sh`, `seed/seed.py` | `make up && make init-db && make seed` |
| N-12 | `docker-compose.lite.yml` / `docker-compose.yml` | lite on 16 GB |
