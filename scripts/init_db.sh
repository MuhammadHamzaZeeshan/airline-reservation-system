#!/usr/bin/env bash
# Idempotent: enable extensions, register Citus workers (and, with HA=1, streaming replicas), create + distribute the schema.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
PSQL() { local svc=$1; shift; docker compose exec -T "$svc" psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"; }

echo "== extensions on every node"
for n in coordinator worker1 worker2; do PSQL "$n" -c "CREATE EXTENSION IF NOT EXISTS citus;"; done
echo "== register workers"
for w in worker1 worker2; do
  PSQL coordinator -c "SELECT citus_add_node('$w', 5432) WHERE NOT EXISTS (SELECT 1 FROM pg_dist_node WHERE nodename='$w' AND noderole='primary');" >/dev/null
done
# pgvector and pg_trgm are installed on each node separately (DDL propagation off so the coordinator does not re-send them)
for n in coordinator worker1 worker2; do
  PSQL "$n" -c "SET citus.enable_ddl_propagation TO off; CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
done

if [ "${HA:-0}" = "1" ]; then
  echo "== register streaming replicas as Citus secondary nodes (read-only queries) and enable synchronous commit to them"
  for w in worker1 worker2; do
    PSQL coordinator -c "SELECT citus_add_secondary_node('${w}-replica', 5432, '$w', 5432) WHERE NOT EXISTS (SELECT 1 FROM pg_dist_node WHERE nodename='${w}-replica');" >/dev/null
    # synchronous replication => a committed booking is on the replica before the client is answered => no committed booking lost on failover
    PSQL "$w" -c "ALTER SYSTEM SET synchronous_standby_names = '*'; SELECT pg_reload_conf();" >/dev/null
  done
fi

echo "== schema + distribution"
PSQL coordinator < sql/001_schema.sql
PSQL coordinator < sql/002_citus_distribute.sql
echo "== active workers"
PSQL coordinator -c "SELECT nodename, nodeport, noderole, isactive FROM pg_dist_node ORDER BY nodeid;"
