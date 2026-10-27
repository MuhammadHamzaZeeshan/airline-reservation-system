"""Accounts and the O(1) uniqueness check.

Why O(1) with many coordinators: username_registry is hash-distributed BY username, so every lookup/insert touches exactly one
shard no matter which coordinator or API node receives it. The registry PRIMARY KEY on that shard is the single source of truth
(two concurrent registrations of the same name: exactly one INSERT wins). A Redis Bloom filter is only a fast pre-check
("definitely free" without touching Postgres). Bloom may say "maybe taken" falsely -> we then ask the registry. It is never
trusted for 'taken' and only trusted for 'free' when `bloom:ready` is set (fully loaded).
"""
import logging

from app.core.errors import ApiError

log = logging.getLogger("ars")
BLOOM_USERS, BLOOM_EMAILS, BLOOM_READY = "bloom:usernames", "bloom:emails", "bloom:ready"


async def _bloom_ready(r) -> bool:
    try:
        return r is not None and bool(await r.exists(BLOOM_READY))
    except Exception:  # noqa: BLE001
        return False


async def _bloom_exists(r, key: str, val: str) -> bool | None:
    """True=maybe present, False=definitely absent, None=unknown (Redis/Bloom unavailable)."""
    try:
        return bool(await r.execute_command("BF.EXISTS", key, val))
    except Exception:  # noqa: BLE001
        return None


async def _bloom_add(r, key: str, val: str) -> None:
    try:
        await r.execute_command("BF.ADD", key, val)
    except Exception:  # noqa: BLE001
        pass


async def username_taken(pool, r, username: str) -> bool:
    if await _bloom_ready(r) and (await _bloom_exists(r, BLOOM_USERS, username)) is False:
        return False
    return await pool.fetchval("SELECT 1 FROM username_registry WHERE username = $1", username) is not None


async def email_taken(pool, r, email: str) -> bool:
    if await _bloom_ready(r) and (await _bloom_exists(r, BLOOM_EMAILS, email)) is False:
        return False
    return await pool.fetchval("SELECT 1 FROM email_registry WHERE email = $1", email) is not None


async def register(pool, r, username: str, email: str, password_hash: str, full_name: str) -> int:
    """Sequence: registry PK inserts (truth) -> users row -> Bloom add. Compensate (delete) on any failure.
    No cross-shard transaction is needed because each step is idempotent/compensable."""
    user_id = await pool.fetchval("SELECT nextval('user_id_seq')")
    tag = await pool.execute("INSERT INTO username_registry (username, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", username, user_id)
    if tag != "INSERT 0 1":
        raise ApiError(409, "USERNAME_TAKEN", "username already taken")
    try:
        tag = await pool.execute("INSERT INTO email_registry (email, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", email, user_id)
        if tag != "INSERT 0 1":
            raise ApiError(409, "EMAIL_TAKEN", "email already registered")
        await pool.execute("INSERT INTO users (user_id, username, email, password_hash, full_name) VALUES ($1,$2,$3,$4,$5)",
                           user_id, username, email, password_hash, full_name)
    except BaseException:
        # compensate so the name is not burned by a half-finished registration
        await pool.execute("DELETE FROM username_registry WHERE username = $1 AND user_id = $2", username, user_id)
        await pool.execute("DELETE FROM email_registry WHERE email = $1 AND user_id = $2", email, user_id)
        raise
    if r is not None:
        await _bloom_add(r, BLOOM_USERS, username)
        await _bloom_add(r, BLOOM_EMAILS, email)
    return user_id


async def find_for_login(pool, ident: str):
    """Login by username or email; goes through the registries (single shard) to find the user_id, then one users shard."""
    ident = ident.strip()
    reg = "email_registry WHERE email" if "@" in ident else "username_registry WHERE username"
    uid = await pool.fetchval(f"SELECT user_id FROM {reg} = $1", ident)  # noqa: S608 - fixed literals, value parameterised
    if uid is None:
        return None
    return await pool.fetchrow("SELECT user_id, username, password_hash, is_admin, full_name, email FROM users WHERE user_id = $1", uid)
