import httpx
from fastapi import APIRouter, Depends, Request

from app.core.errors import ApiError
from app.core.security import CurrentUser, admin_user
from app.services import analytics_service

router = APIRouter(prefix="/v1/admin", tags=["admin"])

ALLOWED = {"load-test", "heavy-load", "race-test", "kill-api", "kill-worker", "restore-all"}


@router.get("/dashboard")
async def dashboard(request: Request, _: CurrentUser = Depends(admin_user)):
    return await analytics_service.dashboard(request.app)


@router.get("/cluster")
async def cluster(request: Request, _: CurrentUser = Depends(admin_user)):
    return await analytics_service.cluster(request.app)


async def _simctl(request: Request, method: str, path: str, **kw):
    s = request.app.state.settings
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.request(method, f"{s.simctl_url}{path}", headers={"X-Token": s.simctl_token}, **kw)
            r.raise_for_status()
            return r.json()
    except Exception:  # noqa: BLE001
        raise ApiError(503, "DEGRADED", "simulation controller unavailable")


@router.post("/simulate/{name}")
async def simulate(name: str, request: Request, _: CurrentUser = Depends(admin_user)):
    if name not in ALLOWED:
        raise ApiError(400, "VALIDATION_ERROR", f"unknown simulation. allowed: {', '.join(sorted(ALLOWED))}")
    return await _simctl(request, "POST", f"/run/{name}")


@router.get("/simulate/{job_id}/log")
async def sim_log(job_id: str, request: Request, _: CurrentUser = Depends(admin_user)):
    return await _simctl(request, "GET", f"/log/{job_id}")
