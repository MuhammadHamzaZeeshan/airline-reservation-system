#!/usr/bin/env bash
# Runs every chaos scenario that the running stack supports and prints one verdict.
cd "$(dirname "$0")"
rc=0
for s in kill_api_node kill_redis kill_stores kill_nginx failover_worker failover_coordinator; do
  echo; echo "=================== $s"; ./$s.sh || rc=1
done
echo; [ $rc = 0 ] && echo "CHAOS: ALL SCENARIOS PASSED" || echo "CHAOS: SOME SCENARIOS FAILED"
exit $rc
