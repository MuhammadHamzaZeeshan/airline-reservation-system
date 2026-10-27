# Demo script (about 10 minutes)
1. **Architecture (1 min)**: open `docs/ARCHITECTURE_REPORT.md` diagram. Say: "Postgres/Citus is the truth; every other store has one job and the system works without it."
2. **Sharding (1 min)**: `make verify-distribution`. Point at: flight-keyed tables share one colocation id; registries are distributed by username/email; reference tables replicated.
3. **Search (1 min)**: app -> Karachi to London, sort by price then duration, filter max price, click Load more. Say: "keyset cursor, no OFFSET; results in N ms, repeat shows `cached`."
4. **Booking + race (2 min)**: open the demo flight with 1 seat (900000001) in two browsers (two users). Both choose the same seat: one gets "held by another customer". Let the hold expire or release, then book: confirmation page shows PNR and tickets.
5. **Race tests (1 min)**: `make test-race` (or the Admin panel button). Say the six scenarios and "0 double bookings, 0 negative inventory".
6. **Heavy load (2 min)**: Admin -> Heavy load, with Grafana :3000 open. Show rate, p95, 429 shedding rising, 5xx flat at zero.
7. **Failure (1 min)**: Admin -> Kill API node: users keep browsing; then `./chaos/kill_redis.sh`: app degrades, booking still correct. (Full stack: `./chaos/failover_worker.sh`.)
8. **Polyglot (1 min)**: Network page (Neo4j), Similar button (pgvector), Admin dashboard (ClickHouse).

# Viva Q&A
**Why Citus and why shard by flight_id?** Every booking touches one flight, so seats, inventory, booking, tickets and outbox co-locate on one shard: the confirm is a single-node transaction, no two-phase commit. Users are sharded by user_id, registries by the unique value.

**How do you prevent double booking?** Four guards in one transaction: `INSERT seat ... ON CONFLICT DO NOTHING` (PK flight_id+seat_no, rowcount must be 1), `UPDATE inventory ... WHERE available >= n`, a CHECK constraint, and the idempotency unique key. Redis holds are only advisory.

**What if Redis is down?** Search is uncached, rate limiting fails open (Nginx still limits), holds degrade to DB guards. Verified by `chaos/kill_redis.sh` and a test run with Redis stopped.

**What is the last-seat race and how is it solved?** Many buyers want the final seat. The seat INSERT conflict and the `available >= n` update let exactly one transaction commit; the others get 409. `test_last_seat_many_buyers` runs 20 at once.

**How is the username check O(1) with several coordinators?** The registry is distributed by username; a lookup is a primary-key probe on one shard regardless of which coordinator receives it. A Bloom filter only shortcuts the "free" case. Claiming the name is an INSERT whose PK makes exactly one concurrent registration win.

**Why keyset pagination?** OFFSET cost grows with page depth and results shift under inserts. Keyset uses the sort keys plus flight_id as a stable tie-breaker and an index seek.

**How do you survive a worker failure?** Full stack: each worker has a synchronous streaming replica; `failover_worker.sh` promotes it and takes over the DNS name; synchronous commit means no acknowledged booking is lost. Cost: writes wait if the replica is down. Lite stack has no replicas, and says so.

**Why an outbox?** The event must exist exactly when the booking exists. It is written in the booking transaction and drained later; sinks are idempotent, so at-least-once delivery is safe, and a down ClickHouse/Mongo only delays analytics.

**Why not SKIP LOCKED?** Citus cannot lock rows across shards in one query; idempotent sinks give the same safety.

**What is eventually consistent?** Availability counters (reconciler), dashboards, graph (hourly), search cache (30 s). What is strongly consistent: seats, bookings, uniqueness.

**How do you shed load?** Nginx per-IP token bucket and the API's Redis token bucket answer 429; bounded pgbouncer/asyncpg pools and uvicorn backlog prevent collapse.

**What are the limits of this work?** Real numbers for 50M rows, 5,000 users and failover time must come from your hardware (commands provided). Failover is scripted, not automatic. Seats store only sold rows.
