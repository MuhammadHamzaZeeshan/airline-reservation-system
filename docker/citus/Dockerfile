# Citus 12.1 (PostgreSQL 16) + pgvector. pg_trgm ships with postgres contrib.
FROM citusdata/citus:12.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
COPY docker/citus/replica-entrypoint.sh /replica-entrypoint.sh
COPY docker/citus/init-replication.sh /docker-entrypoint-initdb.d/010-init-replication.sh
RUN chmod +x /replica-entrypoint.sh /docker-entrypoint-initdb.d/010-init-replication.sh
