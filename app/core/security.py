"""bcrypt password hashing (off the event loop) and JWT auth dependencies."""
import asyncio
import time
import uuid
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.errors import ApiError


async def hash_password(pw: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return (await asyncio.to_thread(bcrypt.hashpw, pw.encode(), bcrypt.gensalt(rounds))).decode()


async def verify_password(pw: str, hashed: str) -> bool:
    try:
        return await asyncio.to_thread(bcrypt.checkpw, pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, username: str, is_admin: bool) -> tuple[str, int]:
    s = get_settings()
    exp = int(time.time()) + s.jwt_expire_minutes * 60
    tok = jwt.encode({"sub": str(user_id), "usr": username, "adm": is_admin, "exp": exp, "jti": uuid.uuid4().hex},
                     s.jwt_secret, algorithm="HS256")
    return tok, s.jwt_expire_minutes * 60


class CurrentUser:
    def __init__(self, user_id: int, username: str, is_admin: bool, jti: str, exp: int):
        self.user_id, self.username, self.is_admin, self.jti, self.exp = user_id, username, is_admin, jti, exp


async def current_user(request: Request) -> CurrentUser:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "missing bearer token")
    try:
        c: dict[str, Any] = jwt.decode(auth[7:], get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "invalid or expired token")
    r = request.app.state.redis
    try:  # logout blacklist; if Redis is down we simply cannot check it (graceful degradation)
        if r is not None and await r.exists(f"revoked:{c['jti']}"):
            raise ApiError(401, "UNAUTHORIZED", "token revoked")
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        pass
    return CurrentUser(int(c["sub"]), c["usr"], bool(c.get("adm")), c["jti"], int(c["exp"]))


async def admin_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise ApiError(403, "FORBIDDEN", "admin only")
    return user
