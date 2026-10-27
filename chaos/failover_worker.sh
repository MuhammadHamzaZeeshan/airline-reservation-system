#!/usr/bin/env bash
# FULL stack only (N-8): kill the primary of Citus worker 1, promote its synchronous replica, take over its DNS name.
# PASS: service restored in < 30 s AND no committed booking lost.
source "$(dirname "$0")/lib.sh"
docker inspect ars-worker1-replica >/dev/null 2>&1 || { echo "SKIP  needs the full stack (make up-full && make init-db-ha)"; exit 0; }
PSQL() { docker compose exec -T coordinator psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "$1"; }
for i in 1 2 3; do python3 chaos/probe.py book "$BASE" >/dev/null || true; done
BEFORE=$(PSQL "SELECT count(*) FROM bookings WHERE flight_id > 900000000")
echo "demo bookings before failure: $BEFORE"
T0=$(date +%s)
docker stop ars-worker1 >/dev/null
docker exec -u postgres ars-worker1-replica pg_ctl promote -D /var/lib/postgresql/data >/dev/null
docker network disconnect ars_ars ars-worker1-replica
docker network connect --alias worker1 --alias worker1-replica ars_ars ars-worker1-replica
until curl -sf "$BASE/v1/flights/search?origin=KHI&destination=LHR&limit=1&date_to=$(date -u -d '+90 days' +%Y-%m-%dT00:00:00Z)" >/dev/null; do
  sleep 1; [ $(( $(date +%s) - T0 )) -gt 90 ] && break
done
T=$(( $(date +%s) - T0 ))
echo "service restored after ${T}s"
AFTER=$(PSQL "SELECT count(*) FROM bookings WHERE flight_id > 900000000")
check "failover completed in < 30 s (${T}s)" test "$T" -lt 30
check "no committed booking lost ($BEFORE -> $AFTER)" test "$AFTER" -ge "$BEFORE"
check "API stayed alive through failover" probe 5 "$BASE"
echo "NOTE: worker1 is now served by the promoted replica; run 'make clean' + 'make up-full' to rebuild the topology."
[ -z "${FAILED:-}" ]
