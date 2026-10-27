#!/usr/bin/env bash
# FULL stack only: the second Nginx (port HTTP_PORT_2) keeps serving when the first dies.
source "$(dirname "$0")/lib.sh"
docker inspect ars-nginx2 >/dev/null 2>&1 || { echo "SKIP  needs the full stack (make up-full)"; exit 0; }
docker stop ars-nginx >/dev/null
check "nginx #1 killed: nginx #2 serves traffic" probe 10 "$BASE2"
docker start ars-nginx >/dev/null
[ -z "${FAILED:-}" ]
