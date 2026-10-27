from fastapi import APIRouter, Query, Request

from app.services import graph_service

router = APIRouter(prefix="/v1/routes", tags=["routes"])


@router.get("/network")
async def network(request: Request, limit: int = Query(default=250, ge=10, le=1000)):
    return await graph_service.network(request.app, limit)


@router.get("/path")
async def path(request: Request, origin: str = Query(min_length=3, max_length=3), destination: str = Query(min_length=3, max_length=3),
               max_stops: int = Query(default=2, ge=0, le=3)):
    return await graph_service.paths(request.app, origin, destination, max_stops)
