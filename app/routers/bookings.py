from fastapi import APIRouter, Depends, Header, Request

from app.core.security import CurrentUser, current_user
from app.schemas.models import BookingIn
from app.services import booking_service

router = APIRouter(prefix="/v1/bookings", tags=["bookings"])


@router.post("", status_code=201)
async def confirm(body: BookingIn, request: Request, user: CurrentUser = Depends(current_user),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return await booking_service.confirm(request.app, user, body, idempotency_key)


@router.get("")
async def mine(request: Request, user: CurrentUser = Depends(current_user)):
    return {"items": await booking_service.my_bookings(request.app, user.user_id)}


@router.delete("/{flight_id}/{pnr}")
async def cancel(flight_id: int, pnr: str, request: Request, user: CurrentUser = Depends(current_user)):
    return await booking_service.cancel(request.app, user, flight_id, pnr)
