#!/usr/bin/env bash
# One-command test summary: unit tests, automated race tests, k6 baseline (search p95), data invariants.
set -uo pipefail
cd "$(dirname "$0")/.."
source .env
DC="docker compose"
declare -A R
run() { local name=$1; shift; echo "---- $name"; if "$@"; then R[$name]=PASS; else R[$name]=FAIL; fi; }

run "unit tests"        $DC exec -T api1 python -m pytest app/tests -q --no-header
run "race + API tests"  $DC exec -T -e API_URL=http://nginx:80 -e PG_TEST_HOST=coordinator api1 python -m pytest loadtest/race_tests -q --no-header
run "k6 baseline (500 VUs, search p95<300ms)" docker exec ars-k6 k6 run --quiet /scripts/baseline.js
run "inventory invariants" bash -c "$DC exec -T coordinator psql -U $POSTGRES_USER -d $POSTGRES_DB -tA -f - < sql/verify_inventory.sql | awk -F'|' '\$2!=0{bad=1} END{exit bad}'"

echo; echo "================ SUMMARY ================"
for k in "unit tests" "race + API tests" "k6 baseline (500 VUs, search p95<300ms)" "inventory invariants"; do printf "%-48s %s\n" "$k" "${R[$k]}"; done
for v in "${R[@]}"; do [ "$v" = PASS ] || exit 1; done
echo "ALL PASSED"
