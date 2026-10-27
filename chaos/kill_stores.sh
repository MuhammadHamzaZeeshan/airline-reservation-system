#!/usr/bin/env bash
# MongoDB, Neo4j, ClickHouse are non-critical: search + booking unaffected, outbox buffers events and drains after recovery.
source "$(dirname "$0")/lib.sh"
PSQL() { docker compose exec -T coordinator psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "$1"; }
docker stop ars-mongo ars-neo4j ars-clickhouse >/dev/null; sleep 3
check "stores killed: search stays up" probe 10 "$BASE"
check "stores killed: booking still works" python3 chaos/probe.py book "$BASE"
check "stores killed: route network falls back to PostgreSQL" bash -c "curl -s $BASE/v1/routes/network | grep -q '\"nodes\"'"
sleep 3; echo "outbox pending while stores are down: $(PSQL 'SELECT count(*) FROM outbox WHERE processed_at IS NULL')"
docker start ars-mongo ars-neo4j ars-clickhouse >/dev/null
echo "waiting up to 90 s for the outbox to drain..."
for i in $(seq 1 30); do n=$(PSQL "SELECT count(*) FROM outbox WHERE processed_at IS NULL"); [ "$n" = 0 ] && break; sleep 3; done
check "outbox drained after recovery (pending=$n)" test "$n" = 0
[ -z "${FAILED:-}" ]
