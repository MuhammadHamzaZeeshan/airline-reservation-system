from fastapi import APIRouter, Depends, Request

from app.core.security import CurrentUser, current_user
from app.schemas.models import HoldIn
from app.services import hold_service

router = APIRouter(prefix="/v1/holds", tags=["holds"])


@router.post("", status_code=201)
async def create(body: HoldIn, request: Request, user: CurrentUser = Depends(current_user)):
    return await hold_service.create_hold(request.app, user, body.flight_id, body.seats)


@router.delete("/{hold_id}", status_code=204)
async def delete(hold_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    await hold_service.release(request.app, hold_id, user.user_id)
