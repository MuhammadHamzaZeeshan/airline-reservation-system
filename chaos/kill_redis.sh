#!/usr/bin/env bash
# Redis (holds, cache, Bloom, rate limit) is advisory: with it gone search works and bookings fall back to the DB guards.
source "$(dirname "$0")/lib.sh"
docker stop ars-redis >/dev/null; sleep 3
check "redis killed: search + health stay up" probe 10 "$BASE"
check "redis killed: /health reports degraded (not down)" bash -c "curl -s $BASE/health | grep -q degraded"
check "redis killed: booking still correct (201 or clean 409, never 5xx)" python3 chaos/probe.py book "$BASE"
docker start ars-redis >/dev/null
echo "redis restarted"
[ -z "${FAILED:-}" ]
