#!/usr/bin/env bash
cd "$(dirname "$0")/.."
source .env
BASE="http://127.0.0.1:${HTTP_PORT}"
BASE2="http://127.0.0.1:${HTTP_PORT_2}"
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILED=1; }
check() { local name=$1; shift; if "$@"; then pass "$name"; else fail "$name"; fi; }
probe() { python3 chaos/probe.py probe "$1" "$2"; }
