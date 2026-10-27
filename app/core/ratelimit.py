"""Distributed token-bucket rate limiter in Redis (one atomic Lua call). Shared by all API nodes.
Fail-OPEN: if Redis is down we do not rate limit in-app (Nginx still limits per IP), so Redis loss never causes an outage."""
import time

from fastapi import Request
from fastapi.responses import JSONResponse

LUA = """
local k=KEYS[1]; local rate=tonumber(ARGV[1]); local burst=tonumber(ARGV[2]); local now=tonumber(ARGV[3])
local d=redis.call('HMGET',k,'t','ts'); local t=tonumber(d[1]); local ts=tonumber(d[2])
if t==nil then t=burst; ts=now end
t=math.min(burst, t+(now-ts)*rate)
local ok=0
if t>=1 then t=t-1; ok=1 end
redis.call('HSET',k,'t',t,'ts',now); redis.call('EXPIRE',k,math.ceil(burst/rate)+1)
return ok
"""


async def rate_limit_middleware(request: Request, call_next):
    app = request.app
    s, r = app.state.settings, app.state.redis
    if r is None or request.url.path.startswith(("/health", "/metrics")):
        return await call_next(request)
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    try:
        ok = await r.eval(LUA, 1, f"rl:{ip}", s.rate_limit_rps, s.rate_limit_burst, time.time())
    except Exception:  # noqa: BLE001
        return await call_next(request)
    if not ok:
        return JSONResponse(status_code=429, headers={"Retry-After": "1"},
                            content={"error": "RATE_LIMITED", "message": "too many requests",
                                     "request_id": getattr(request.state, "request_id", "-")})
    return await call_next(request)
