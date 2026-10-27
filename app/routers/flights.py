from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.db.mongo import fire_event, fire_view
from app.schemas.models import SearchParams
from app.services import inventory, recommendation_service, search_service

router = APIRouter(prefix="/v1/flights", tags=["flights"])


@router.get("/search")
async def search(request: Request, p: Annotated[SearchParams, Query()]):
    out = await search_service.search(request.app, p)
    fire_event(request.app.state.mongo, "search_events", {"params": p.model_dump(mode="json", exclude_none=True), "count": out.get("count"), "took_ms": out["took_ms"],
                                                           "cached": out["cached"], "node": request.app.state.settings.node_name})
    return out


@router.get("/{flight_id}")
async def get_flight(flight_id: int, request: Request):
    fl = await inventory.get_flight(request.app.state.pg_pool, flight_id)
    fire_view(request.app.state.mongo, flight_id)
    return {"flight_id": fl["flight_id"], "flight_no": fl["flight_no"], "origin_id": fl["origin_id"], "dest_id": fl["dest_id"],
            "departure_ts": fl["departure_ts"].isoformat(), "arrival_ts": fl["arrival_ts"].isoformat(), "price": float(fl["price"]), "seats_left": fl["seats_left"]}


@router.get("/{flight_id}/availability")
async def availability(flight_id: int, request: Request):
    return await inventory.availability(request.app, flight_id)


@router.get("/{flight_id}/seatmap")
async def seatmap(flight_id: int, request: Request):
    return await inventory.seat_map(request.app, flight_id)


@router.get("/{flight_id}/similar")
async def similar(flight_id: int, request: Request, limit: int = Query(default=8, ge=1, le=20)):
    return await recommendation_service.similar(request.app, flight_id, limit)
