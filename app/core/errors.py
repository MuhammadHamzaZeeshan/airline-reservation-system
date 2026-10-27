"""Error design (DESIGN.md section 4). Body: {"error": CODE, "message": text, "request_id": id}."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def _body(request: Request, code: str, message: str) -> dict:
    return {"error": code, "message": message, "request_id": getattr(request.state, "request_id", "-")}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(request, exc.code, exc.message), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _val(request: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors())
        return JSONResponse(status_code=400, content=_body(request, "VALIDATION_ERROR", msg))

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):
        logging.getLogger("ars").exception("unhandled error", extra={"extra_fields": {"request_id": getattr(request.state, "request_id", "-")}})
        return JSONResponse(status_code=500, content=_body(request, "INTERNAL_ERROR", "unexpected error"))
