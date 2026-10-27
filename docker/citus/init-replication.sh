#!/bin/bash
# Allow streaming-replication connections (trust inside the private compose network only).
echo "host replication all all trust" >> "$PGDATA/pg_hba.conf"
