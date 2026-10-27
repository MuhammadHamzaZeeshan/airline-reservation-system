#!/bin/bash
# Streaming replica: first start clones the primary with pg_basebackup (-R writes standby.signal), then runs as hot standby.
set -e
PGDATA=/var/lib/postgresql/data
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  until pg_isready -h "$PRIMARY_HOST" -U "$POSTGRES_USER"; do echo "waiting for primary $PRIMARY_HOST"; sleep 2; done
  rm -rf "${PGDATA:?}"/* "$PGDATA"/.[!.]* 2>/dev/null || true
  pg_basebackup -h "$PRIMARY_HOST" -U "$POSTGRES_USER" -D "$PGDATA" -R -X stream
  chown -R postgres:postgres "$PGDATA"; chmod 700 "$PGDATA"
fi
exec docker-entrypoint.sh postgres -c hot_standby=on
