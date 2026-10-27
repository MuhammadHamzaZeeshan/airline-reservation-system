#!/usr/bin/env bash
# Verifies P1: every container healthy, API reachable through Nginx, load balanced across both nodes,
# survives loss of one API node, degrades (not fails) when Redis stops, Citus workers registered.
set -uo pipefail
source .env
URL="http://127.0.0.1:${HTTP_PORT}"
fail=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fail=1; }

code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/health"); [ "$code" = 200 ] && ok "GET /health via Nginx = 200" || bad "GET /health = $code"

nodes=$(for i in $(seq 1 30); do curl -s -D - -o /dev/null "$URL/health/live" | grep -i '^x-node' | tr -d '\r'; done | sort -u | wc -l)
[ "$nodes" -ge 2 ] && ok "traffic balanced across $nodes API nodes" || bad "only $nodes API node answered"

workers=$(docker compose exec -T coordinator psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM citus_get_active_worker_nodes();" | tr -d '\r')
[ "$workers" -ge 2 ] && ok "Citus has $workers active workers" || bad "Citus workers = $workers (run make init-db)"

docker compose stop api1 >/dev/null 2>&1; sleep 1
bad_codes=0; for i in $(seq 1 20); do c=$(curl -s -o /dev/null -w '%{http_code}' "$URL/health/live"); [ "$c" = 200 ] || bad_codes=$((bad_codes+1)); done
[ "$bad_codes" -eq 0 ] && ok "api1 stopped: 20/20 requests still 200" || bad "api1 stopped: $bad_codes/20 requests failed"
docker compose start api1 >/dev/null 2>&1

docker compose stop redis >/dev/null 2>&1; sleep 3
body=$(curl -s "$URL/health"); code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")
{ [ "$code" = 200 ] && echo "$body" | grep -q degraded; } && ok "redis stopped: API up, status=degraded" || bad "redis stopped: code=$code body=$body"
docker compose start redis >/dev/null 2>&1

[ "$fail" -eq 0 ] && echo "ALL P1 CHECKS PASSED" || { echo "SOME P1 CHECKS FAILED"; exit 1; }
