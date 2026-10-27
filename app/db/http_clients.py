"""Thin async HTTP helpers for ClickHouse (HTTP interface) and Prometheus."""
import httpx


async def ch_query(s, sql: str) -> list[dict]:
    if not s.clickhouse_url:
        raise RuntimeError("clickhouse not configured")
    async with httpx.AsyncClient(timeout=10, auth=(s.clickhouse_user, s.clickhouse_password)) as c:
        r = await c.post(s.clickhouse_url, content=sql + " FORMAT JSON")
        r.raise_for_status()
        return r.json()["data"]
