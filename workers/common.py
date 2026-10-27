import asyncio
import json
import logging
import os
import sys

import asyncpg

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), stream=sys.stdout,
                    format='{"ts":"%(asctime)s","level":"%(levelname)s","worker":"%(name)s","msg":"%(message)s"}')


def env(k: str, d: str = "") -> str:
    return os.getenv(k, d)


async def pg_pool(min_size=1, max_size=4):
    """Retry until Postgres is reachable (workers must survive start-up ordering and failovers)."""
    while True:
        try:
            return await asyncpg.create_pool(host=env("PG_HOST", "pgbouncer"), port=int(env("PG_PORT", "5432")), user=env("POSTGRES_USER", "ars"),
                                             password=env("POSTGRES_PASSWORD"), database=env("POSTGRES_DB", "ars"), min_size=min_size,
                                             max_size=max_size, statement_cache_size=0, command_timeout=60)
        except Exception as e:  # noqa: BLE001
            logging.getLogger("common").warning("postgres not ready: %s", e)
            await asyncio.sleep(3)
