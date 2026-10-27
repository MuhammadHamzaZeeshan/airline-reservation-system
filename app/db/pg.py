"""asyncpg pool + helpers.

PgBouncer runs in TRANSACTION pooling mode => no server-side prepared statements (statement_cache_size=0) and
session state must not be relied upon. Replica routing therefore uses SET LOCAL inside a transaction.
"""
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import Settings


async def create_pool(s: Settings) -> asyncpg.Pool | None:
    """Return a pool, or None if Postgres is unreachable (API stays up and /health reports it)."""
    try:
        return await asyncpg.create_pool(
            host=s.pg_host, port=s.pg_port, user=s.postgres_user, password=s.postgres_password,
            database=s.postgres_db, min_size=s.pg_pool_min, max_size=s.pg_pool_max,
            statement_cache_size=0, command_timeout=15, timeout=s.dependency_timeout_s,
        )
    except Exception:  # noqa: BLE001
        return None


@asynccontextmanager
async def read_conn(pool: asyncpg.Pool, use_replicas: bool):
    """Connection for read-only queries. With replicas enabled the query runs on a Citus secondary node
    (stale-tolerant: search, listings). Writes and booking decisions NEVER use this."""
    async with pool.acquire() as conn:
        if use_replicas:
            async with conn.transaction(readonly=True):
                await conn.execute("SET LOCAL citus.use_secondary_nodes = 'always'")
                yield conn
        else:
            yield conn
