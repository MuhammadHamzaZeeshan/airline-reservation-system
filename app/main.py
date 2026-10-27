"""FastAPI app factory: stateless node, JSON logs with request_id, Prometheus metrics, Redis rate limit, versioned REST API."""
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from app.core.config import get_settings
from app.core.errors import install_handlers
from app.core.ratelimit import rate_limit_middleware
from app.db.mongo import create_mongo
from app.db.neo4j import create_neo4j
from app.db.pg import create_pool
from app.db.redis import create_redis
from app.routers import admin, auth, bookings, flights, health, holds, routes, users

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_seconds", "HTTP latency", ["method", "route"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10))
POOL_USED = Gauge("pg_pool_connections_in_use", "asyncpg connections in use")
POOL_SIZE = Gauge("pg_pool_connections_total", "asyncpg pool size")
RL = Counter("rate_limited_total", "requests answered 429 by the API")

log = logging.getLogger("ars")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": self.formatTime(record), "level": record.levelname, "msg": record.getMessage()}
        base.update(getattr(record, "extra_fields", {}))
        return json.dumps(base)


def _setup_logging(level: str) -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[h], force=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = app.state.settings
    _setup_logging(s.log_level)
    app.state.pg_pool = await create_pool(s)  # None if unreachable: the node still boots (graceful degradation)
    app.state.redis = create_redis(s)
    app.state.mongo = create_mongo(s.mongo_url)
    app.state.neo4j = create_neo4j(s)
    try:  # Bloom filters for the O(1) username/email pre-check (BF.RESERVE errors if they already exist -> fine)
        for k in ("bloom:usernames", "bloom:emails"):
            try:
                await app.state.redis.execute_command("BF.RESERVE", k, 0.001, 10_000_000)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    log.info("node started", extra={"extra_fields": {"node": s.node_name, "pg": app.state.pg_pool is not None}})
    yield
    if app.state.pg_pool is not None:
        await app.state.pg_pool.close()
    await app.state.redis.aclose()
    if app.state.neo4j is not None:
        await app.state.neo4j.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Airline Reservation System API", version="1.0.0", lifespan=lifespan,
                  description="Versioned public REST API (/v1). Errors: {error, message, request_id}.")
    app.state.settings = get_settings()
    app.state.pg_pool = None
    app.state.redis = None
    app.state.mongo = None
    app.state.neo4j = None
    install_handlers(app)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")  # template, not raw path: bounded metric cardinality
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(request.method, path).observe(elapsed)
        if response.status_code == 429:
            RL.inc()
        pool = request.app.state.pg_pool
        if pool is not None:
            POOL_SIZE.set(pool.get_size())
            POOL_USED.set(pool.get_size() - pool.get_idle_size())
        response.headers["X-Request-ID"] = rid
        response.headers["X-Node"] = request.app.state.settings.node_name
        return response

    app.middleware("http")(rate_limit_middleware)  # added after observe => runs inside it, so 429s are measured too
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in app.state.settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID", "X-Node", "Retry-After"],
    )
    for r in (health.router, auth.router, users.router, flights.router, holds.router, bookings.router, routes.router, admin.router):
        app.include_router(r)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()
