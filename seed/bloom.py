"""Preload the Redis Bloom filters with all seeded usernames/emails, then flag them ready (so 'definitely free' can be trusted)."""
import os

import asyncpg
import redis.asyncio as aioredis


async def load_bloom(dsn: dict) -> None:
    url = os.getenv("REDIS_URL")
    if not url:
        return
    r = aioredis.from_url(url, decode_responses=True)
    try:
        for k in ("bloom:usernames", "bloom:emails"):
            try:
                await r.execute_command("BF.RESERVE", k, 0.001, 10_000_000)
            except Exception as e:  # noqa: BLE001
                if "exists" not in str(e).lower():
                    raise
        conn = await asyncpg.connect(**dsn)
        total = 0
        async with conn.transaction():
            for table, col, key in (("username_registry", "username", "bloom:usernames"), ("email_registry", "email", "bloom:emails")):
                batch = []
                async for rec in conn.cursor(f"SELECT {col} FROM {table}", prefetch=20000):  # noqa: S608 fixed literals
                    batch.append(rec[0])
                    if len(batch) >= 5000:
                        await r.execute_command("BF.MADD", key, *batch)
                        total += len(batch)
                        batch = []
                if batch:
                    await r.execute_command("BF.MADD", key, *batch)
                    total += len(batch)
        await conn.close()
        await r.set("bloom:ready", 1)
        print(f"Bloom filters loaded: {total:,} entries")
    except Exception as e:  # noqa: BLE001
        print(f"Bloom preload skipped ({e}); availability checks will use the registry directly")
    finally:
        await r.aclose()
