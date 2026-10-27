from fastapi import APIRouter, Depends, Request

from app.core.errors import ApiError
from app.core.security import CurrentUser, create_token, current_user, hash_password, verify_password
from app.schemas.models import LoginIn, RegisterIn
from app.services import user_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _pool(request: Request):
    if request.app.state.pg_pool is None:
        raise ApiError(503, "DEGRADED", "database unavailable")
    return request.app.state.pg_pool


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request):
    pool, r = _pool(request), request.app.state.redis
    pw = await hash_password(body.password)  # hash BEFORE touching the DB so a slow bcrypt never holds a connection
    uid = await user_service.register(pool, r, body.username, body.email, pw, body.full_name)
    tok, exp = create_token(uid, body.username, False)
    return {"user_id": uid, "username": body.username, "access_token": tok, "token_type": "bearer", "expires_in": exp}


@router.post("/login")
async def login(body: LoginIn, request: Request):
    pool = _pool(request)
    u = await user_service.find_for_login(pool, body.username)
    if u is None or not await verify_password(body.password, u["password_hash"]):
        raise ApiError(401, "UNAUTHORIZED", "invalid username or password")
    tok, exp = create_token(u["user_id"], u["username"], u["is_admin"])
    return {"user_id": u["user_id"], "username": u["username"], "is_admin": u["is_admin"], "access_token": tok, "token_type": "bearer", "expires_in": exp}


@router.post("/logout", status_code=204)
async def logout(request: Request, user: CurrentUser = Depends(current_user)):
    r = request.app.state.redis
    if r is not None:
        import time
        try:
            await r.set(f"revoked:{user.jti}", 1, ex=max(1, user.exp - int(time.time())))
        except Exception:  # noqa: BLE001
            pass


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)):
    return {"user_id": user.user_id, "username": user.username, "is_admin": user.is_admin}
