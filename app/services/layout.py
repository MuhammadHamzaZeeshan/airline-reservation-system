"""Seat layout is DERIVED from the aircraft type (3-3, rows A-F): business rows first, then premium, then economy.
Only sold seats are stored in PostgreSQL (table seats); free = layout minus sold minus active holds."""
import re

LETTERS = "ABCDEF"
SEAT_RE = re.compile(r"^([0-9]{1,3})([A-F])$")


def class_ranges(br: int, pr: int, er: int) -> list[tuple[str, int, int]]:
    return [("BUSINESS", 1, br), ("PREMIUM", br + 1, br + pr), ("ECONOMY", br + pr + 1, br + pr + er)]


def class_of(seat: str, br: int, pr: int, er: int) -> str | None:
    m = SEAT_RE.match(seat)
    if not m:
        return None
    row = int(m.group(1))
    for cls, lo, hi in class_ranges(br, pr, er):
        if lo <= row <= hi and hi >= lo:
            return cls
    return None


def all_seats(br: int, pr: int, er: int) -> list[tuple[str, str]]:
    out = []
    for cls, lo, hi in class_ranges(br, pr, er):
        out += [(f"{r}{c}", cls) for r in range(lo, hi + 1) for c in LETTERS]
    return out
