"""Redis client factory. Redis is advisory (holds, caches, Bloom); losing it must not take the API down."""
import redis.asyncio as aioredis

from app.core.config import Settings


def create_redis(s: Settings) -> aioredis.Redis:
    return aioredis.from_url(
        s.redis_url,
        socket_timeout=s.dependency_timeout_s,
        socket_connect_timeout=s.dependency_timeout_s,
        health_check_interval=15,
        decode_responses=True,
    )
