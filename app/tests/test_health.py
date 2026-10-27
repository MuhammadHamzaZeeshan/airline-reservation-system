"""P1 tests for /health/live and /health. Uses ASGI transport (no lifespan) with fake dependencies."""
import httpx
import pytest

from app.main import create_app

pytestmark = pytest.mark.asyncio


class FakeConn:
    async def fetchval(self, _q):
        return 1


class FakeAcquire:
    async def __aenter__(self):
        return FakeConn()

    async def __aexit__(self, *a):
        return False


class FakePool:
    def acquire(self):
        return FakeAcquire()

    def get_size(self):
        return 2

    def get_idle_size(self):
        return 1


class FakeRedis:
    def __init__(self, ok=True):
        self.ok = ok

    async def ping(self):
        if not self.ok:
            raise ConnectionError("redis down")
        return True


def client(pool, redis):
    app = create_app()
    app.state.pg_pool = pool
    app.state.redis = redis
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_live_always_200():
    async with client(None, None) as c:
        r = await c.get("/health/live")
    assert r.status_code == 200 and r.json()["status"] == "alive"
    assert "x-request-id" in r.headers


async def test_health_ok():
    async with client(FakePool(), FakeRedis(True)) as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_health_degraded_when_redis_down():
    async with client(FakePool(), FakeRedis(False)) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded" and r.json()["dependencies"]["redis"] == "down"


async def test_health_503_when_postgres_down():
    async with client(None, FakeRedis(True)) as c:
        r = await c.get("/health")
    assert r.status_code == 503 and r.json()["status"] == "down"


async def test_metrics_exposed():
    async with client(FakePool(), FakeRedis(True)) as c:
        await c.get("/health/live")
        r = await c.get("/metrics/")
    assert r.status_code == 200 and "http_requests_total" in r.text
