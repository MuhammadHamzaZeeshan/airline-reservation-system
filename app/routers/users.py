import re

from fastapi import APIRouter, Query, Request

from app.core.errors import ApiError
from app.schemas.models import EMAIL_RE, USERNAME_RE
from app.services import user_service

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/availability")
async def availability(request: Request, username: str | None = Query(default=None, max_length=64), email: str | None = Query(default=None, max_length=254)):
    """O(1) existence check: Bloom pre-check, then ONE registry shard (PK lookup). Same cost on any coordinator."""
    if username is None and email is None:
        raise ApiError(400, "VALIDATION_ERROR", "give username and/or email")
    pool, r = request.app.state.pg_pool, request.app.state.redis
    if pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    out: dict = {}
    if username is not None:
        u = username.strip()
        out["username"] = {"value": u, "valid": bool(USERNAME_RE.match(u))}
        out["username"]["available"] = out["username"]["valid"] and not await user_service.username_taken(pool, r, u)
    if email is not None:
        e = email.strip().lower()
        out["email"] = {"value": e, "valid": bool(EMAIL_RE.match(e))}
        out["email"]["available"] = out["email"]["valid"] and not await user_service.email_taken(pool, r, e)
    return out
