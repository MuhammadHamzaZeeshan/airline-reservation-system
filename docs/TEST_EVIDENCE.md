# Test evidence

## Executed while building (sandbox: 1 CPU core, PostgreSQL 16 + pgvector + Redis, API as 1 uvicorn process; no Docker, no Citus)
```
python -m pytest loadtest/race_tests app/tests -q        ->  36 passed
psql -f sql/verify_inventory.sql                          ->  negative_inventory 0, double_booked_seats 0, mismatches 0
python -m seed.seed --scale 0.004 --force                 ->  200,005 flights; inventory = total - sold for every row; tickets = seats; seats_left = sum(available)
python chaos/probe.py probe/book with Redis stopped       ->  0 failed requests; booking 201 degraded=True; /health = degraded; recovers when Redis returns
npm run build (frontend)                                  ->  tsc type-check clean, vite build OK
```
Race tests that passed (all assert 0 double bookings and 0 negative inventory): same seat two holds, same seat two confirms (Redis bypassed), last seat with 20 buyers,
last seat through holds, N seats / M buyers, idempotent retry storm (6 concurrent identical requests -> one booking), hold expiry, duplicate username race (20 -> 1 winner),
duplicate email race, cancel releases seat, hold on sold seat.

**Not executed here (needs the Docker stack, Citus and enough CPU): the numbers for N-2, N-3, N-4, N-5, N-8, the 50M-row seed, and Citus-specific behaviour.**
A quick smoke test on the 1-core sandbox (client, API, PostgreSQL and Redis sharing one core) gave ~90 requests/s at 50 users; that is a property of the sandbox, not of the system, and is NOT evidence for N-2/N-5.

## Run on your machine
| Command | Expected |
|---|---|
| `make up` | `stack healthy` |
| `make init-db` | worker table shows worker1, worker2 active; distributed table list ends without error |
| `make seed` | `DONE in N min`; Bloom and ClickHouse lines printed |
| `make verify-distribution` | 2 workers, flights shards split evenly, one colocation_id for the six flight-keyed tables |
| `make test-summary` | table with 4 PASS rows and `ALL PASSED` |
| `make load` | k6 thresholds green: `http_req_duration{name:search} p(95)<300`, `http_req_failed rate<0.02` |
| `make load-heavy` | thresholds green; `shed_429` > 0 is expected; no 5xx |
| `make storm` | `booking_outcome{result:server_error}` count 0, then `negative_inventory 0, double_booked_seats 0` |
| `make chaos` | each scenario prints PASS lines; `CHAOS: ALL SCENARIOS PASSED` (full-stack scenarios print SKIP on the lite stack) |
