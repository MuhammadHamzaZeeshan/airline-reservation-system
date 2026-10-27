"""Environment-driven settings (RULES.md: configuration via env, sane lite defaults)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    node_name: str = "api"
    log_level: str = "INFO"

    postgres_db: str = "ars"
    postgres_user: str = "ars"
    postgres_password: str = "change_me_ars_pw"
    pg_host: str = "pgbouncer"
    pg_port: int = 5432
    pg_pool_min: int = 2
    pg_pool_max: int = 10
    use_replicas: bool = False  # route read-only queries to Citus secondary nodes (full stack)

    redis_url: str = "redis://redis:6379/0"
    mongo_url: str = ""
    neo4j_url: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    clickhouse_url: str = ""
    clickhouse_user: str = "ars"
    clickhouse_password: str = ""
    prometheus_url: str = "http://prometheus:9090"
    simctl_url: str = "http://simctl:9000"
    simctl_token: str = ""

    jwt_secret: str = "change_me_to_a_long_random_string"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    hold_ttl_seconds: int = 600
    max_seats_per_booking: int = 9
    rate_limit_rps: float = 200.0     # per client IP, token bucket in Redis
    rate_limit_burst: int = 400
    search_cache_ttl: int = 30
    dependency_timeout_s: float = 2.0
    bcrypt_rounds: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
