"""Pydantic request models (validation -> 400 VALIDATION_ERROR)."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
import re

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=100)

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("username must be 3-32 chars of a-z, A-Z, 0-9, _ or .")
        return v

    @field_validator("email")
    @classmethod
    def _e(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class HoldIn(BaseModel):
    flight_id: int = Field(gt=0)
    seats: list[str] = Field(min_length=1, max_length=9)

    @field_validator("seats")
    @classmethod
    def _s(cls, v: list[str]) -> list[str]:
        out = [s.strip().upper() for s in v]
        if len(set(out)) != len(out) or any(not re.match(r"^[0-9]{1,3}[A-F]$", s) for s in out):
            raise ValueError("seats must be unique and look like 14C")
        return out


class PassengerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    seat_no: str

    @field_validator("seat_no")
    @classmethod
    def _s(cls, v: str) -> str:
        return v.strip().upper()


class BookingIn(BaseModel):
    flight_id: int = Field(gt=0)
    hold_id: str = Field(min_length=1, max_length=80)
    passengers: list[PassengerIn] = Field(min_length=1, max_length=9)


class SearchParams(BaseModel):
    origin: str | None = Field(default=None, max_length=60)
    destination: str | None = Field(default=None, max_length=60)
    airline: str | None = Field(default=None, max_length=60)
    flight_no: str | None = Field(default=None, max_length=12)
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_duration: int | None = Field(default=None, ge=0)
    max_duration: int | None = Field(default=None, ge=0)
    max_stops: int | None = Field(default=None, ge=0, le=3)
    passengers: int = Field(default=1, ge=1, le=9)
    fare_class: str | None = Field(default=None, pattern="^(ECONOMY|PREMIUM|BUSINESS)$")
    sort: str = "departure:asc"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
