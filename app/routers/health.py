"""Health endpoints.

/health/live  - process is up (Docker/Nginx health checks; touches no dependency).
/health       - dependency report. Postgres down -> 503 (core unusable). Redis/Mongo/Neo4j/ClickHouse down -> 200 "degraded"
                (core search + booking keep working: ARCHITECTURE.md section 6).
"""
import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.http_clients import ch_query

router = APIRouter(tags=["health"])


async def check_postgres(pool: Any, timeout: float) -> bool:
    if pool is None:
        return False
    try:
        async def _q() -> int:
            async with pool.acquire() as conn:
                return await conn.fetchval("SELECT 1")

        return (await asyncio.wait_for(_q(), timeout)) == 1
    except Exception:  # noqa: BLE001
        return False


async def check_redis(client: Any, timeout: float) -> bool:
    if client is None:
        return False
    try:
        return bool(await asyncio.wait_for(client.ping(), timeout))
    except Exception:  # noqa: BLE001
        return False


async def _opt(coro, timeout: float) -> str:
    try:
        await asyncio.wait_for(coro, timeout)
        return "up"
    except Exception:  # noqa: BLE001
        return "down"


@router.get("/health/live")
async def live(request: Request) -> dict[str, str]:
    return {"status": "alive", "node": request.app.state.settings.node_name}


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    st = request.app.state
    t = st.settings.dependency_timeout_s
    pg_ok, redis_ok = await asyncio.gather(check_postgres(st.pg_pool, t), check_redis(st.redis, t))
    deps = {"postgres": "up" if pg_ok else "down", "redis": "up" if redis_ok else "down"}
    optional = {}
    if getattr(st, "mongo", None) is not None:
        optional["mongodb"] = _opt(st.mongo.admin.command("ping"), t)
    if getattr(st, "neo4j", None) is not None:
        optional["neo4j"] = _opt(st.neo4j.verify_connectivity(), t)
    if st.settings.clickhouse_url:
        optional["clickhouse"] = _opt(ch_query(st.settings, "SELECT 1"), t)
    if optional:
        for k, v in zip(optional, await asyncio.gather(*optional.values())):
            deps[k] = v
    if not pg_ok:
        status, code = "down", 503
    elif any(v == "down" for v in deps.values()):
        status, code = "degraded", 200
    else:
        status, code = "ok", 200
    return JSONResponse(status_code=code, content={"status": status, "node": st.settings.node_name, "dependencies": deps})
