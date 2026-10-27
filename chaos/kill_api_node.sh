#!/usr/bin/env bash
# N-1: killing an API node must not cause user-visible errors (nginx retries GETs on the surviving node).
source "$(dirname "$0")/lib.sh"
docker stop ars-api1 >/dev/null
check "api1 killed: 15 s of traffic, 0 failures" probe 15 "$BASE"
docker start ars-api1 >/dev/null
echo "api1 restarted"
[ -z "${FAILED:-}" ]
