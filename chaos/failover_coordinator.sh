#!/usr/bin/env bash
# FULL stack only: kill the Citus coordinator, promote the standby, take over the name PgBouncer connects to.
source "$(dirname "$0")/lib.sh"
docker inspect ars-coordinator-standby >/dev/null 2>&1 || { echo "SKIP  needs the full stack"; exit 0; }
T0=$(date +%s)
docker stop ars-coordinator >/dev/null
docker exec -u postgres ars-coordinator-standby pg_ctl promote -D /var/lib/postgresql/data >/dev/null
docker network disconnect ars_ars ars-coordinator-standby
docker network connect --alias coordinator --alias coordinator-standby ars_ars ars-coordinator-standby
until [ "$(curl -s -o /dev/null -w '%{http_code}' $BASE/health)" = 200 ]; do sleep 1; [ $(( $(date +%s) - T0 )) -gt 90 ] && break; done
T=$(( $(date +%s) - T0 ))
check "coordinator failover: /health = 200 again after ${T}s (< 40 s)" test "$T" -lt 40
check "search works through the promoted coordinator" probe 5 "$BASE"
[ -z "${FAILED:-}" ]
