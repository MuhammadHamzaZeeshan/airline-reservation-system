"""Functional API tests: auth, availability, search, sort, cursor pagination, seat map, similar flights, errors."""
import uuid
from datetime import datetime, timezone

import pytest

from .conftest import register

pytestmark = pytest.mark.asyncio
from datetime import timedelta
SEARCH = {"origin": "Karachi", "destination": "LHR", "limit": 10,
          "date_from": datetime.now(timezone.utc).isoformat(), "date_to": (datetime.now(timezone.utc) + timedelta(days=364)).isoformat()}


async def test_health(http):
    r = await http.get("/health")
    assert r.status_code == 200 and r.json()["status"] in ("ok", "degraded")


async def test_auth_flow(http):
    u = await register(http)
    me = await http.get("/v1/auth/me", headers=u["h"])
    assert me.status_code == 200 and me.json()["username"] == u["name"]
    assert (await http.get("/v1/auth/me")).status_code == 401
    lg = await http.post("/v1/auth/login", json={"username": u["name"], "password": "Passw0rd!x"})
    assert lg.status_code == 200
    assert (await http.post("/v1/auth/login", json={"username": u["name"], "password": "wrong"})).status_code == 401
    assert (await http.post("/v1/auth/logout", headers=u["h"])).status_code == 204


async def test_validation_errors(http):
    r = await http.post("/v1/auth/register", json={"username": "a", "email": "bad", "password": "x"})
    assert r.status_code == 400 and r.json()["error"] == "VALIDATION_ERROR" and "request_id" in r.json()


async def test_username_availability(http):
    u = await register(http)
    t = (await http.get("/v1/users/availability", params={"username": u["name"], "email": f"{u['name']}@test.local"})).json()
    assert t["username"]["available"] is False and t["email"]["available"] is False
    f = (await http.get("/v1/users/availability", params={"username": f"free_{uuid.uuid4().hex[:10]}"})).json()
    assert f["username"]["available"] is True
    assert (await http.get("/v1/users/availability")).status_code == 400


async def test_search_too_broad(http):
    r = await http.get("/v1/flights/search", params={"origin": "Karachi"})
    assert r.status_code == 400 and r.json()["error"] == "QUERY_TOO_BROAD"


async def test_search_text_and_numeric(http):
    r = await http.get("/v1/flights/search", params={**SEARCH, "max_price": 600, "max_stops": 2, "sort": "price:asc"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and all(i["origin_code"] == "KHI" and i["dest_code"] == "LHR" and i["price"] <= 600 and i["stops"] <= 2 for i in items)
    prices = [i["price"] for i in items]
    assert prices == sorted(prices)
    assert all(c["available"] >= 0 for i in items for c in i["classes"])


async def test_cursor_pagination_multikey(http):
    seen, cursor, last = [], None, None
    for _ in range(40):
        p = {**SEARCH, "limit": 3, "sort": "price:desc,duration:asc"}
        if cursor:
            p["cursor"] = cursor
        j = (await http.get("/v1/flights/search", params=p)).json()
        for i in j["items"]:
            key = (-i["price"], i["duration_min"], i["flight_id"])
            assert last is None or key >= last, "page order broken"
            last = key
            seen.append(i["flight_id"])
        cursor = j["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) and len(seen) >= 4, "duplicates or too few rows across pages"
    bad = await http.get("/v1/flights/search", params={**SEARCH, "cursor": "garbage"})
    assert bad.status_code == 400


async def test_invalid_sort_is_rejected_not_injected(http):
    r = await http.get("/v1/flights/search", params={**SEARCH, "sort": "price; DROP TABLE flights--"})
    assert r.status_code == 400


async def test_demo_flights_availability_and_seatmap(http):
    j = (await http.get("/v1/flights/900000003/availability")).json()
    eco = next(c for c in j["classes"] if c["fare_class"] == "ECONOMY")
    assert eco["db_available"] == 3
    sm = (await http.get("/v1/flights/900000003/seatmap")).json()
    assert sum(1 for s in sm["seats"] if s["status"] == "available") == 3
    assert sm["layout"] == "3-3"


async def test_similar_flights(http):
    s = (await http.get("/v1/flights/search", params={**SEARCH, "limit": 1})).json()["items"][0]
    j = (await http.get(f"/v1/flights/{s['flight_id']}/similar")).json()
    assert all(i["origin_code"] == "KHI" and i["flight_id"] != s["flight_id"] for i in j["items"])


async def test_routes_and_path(http):
    n = (await http.get("/v1/routes/network")).json()
    assert n["edges"]
    p = (await http.get("/v1/routes/path", params={"origin": "KHI", "destination": "LHR"})).json()
    assert p["shortest"] == ["KHI", "LHR"]


async def test_my_bookings_requires_auth(http):
    assert (await http.get("/v1/bookings")).status_code == 401
    u = await register(http)
    assert (await http.get("/v1/bookings", headers=u["h"])).json() == {"items": []}


async def test_admin_forbidden_for_normal_user(http):
    u = await register(http)
    assert (await http.get("/v1/admin/cluster", headers=u["h"])).status_code == 403


async def test_flight_detail_and_404(http):
    r = await http.get("/v1/flights/900000001")
    assert r.status_code == 200 and r.json()["flight_no"] == "DM101"
    assert (await http.get("/v1/flights/987654321012")).status_code == 404


async def test_hold_release_frees_seat(http, db, users, make_flight):
    from .conftest import hold
    fid, free = await make_flight(2)
    a, b = await users(2)
    h = (await hold(http, a, fid, [free[0]])).json()
    assert (await http.delete(f"/v1/holds/{h['hold_id']}", headers=b["h"])).status_code == 403   # not b's hold
    assert (await http.delete(f"/v1/holds/{h['hold_id']}", headers=a["h"])).status_code == 204
    assert (await hold(http, b, fid, [free[0]])).status_code == 201                                # seat is free again


async def test_hold_validation(http, users, make_flight):
    from .conftest import hold
    fid, free = await make_flight(2)
    (u,) = await users(1)
    assert (await hold(http, u, fid, ["99Z"])).status_code == 400                                  # malformed seat
    assert (await hold(http, u, fid, ["200A"])).status_code == 400                                 # row does not exist
    assert (await http.post("/v1/holds", json={"flight_id": fid, "seats": [free[0]]})).status_code == 401


async def test_booking_requires_idempotency_key(http, users, make_flight):
    from .conftest import hold
    fid, free = await make_flight(2)
    (u,) = await users(1)
    h = (await hold(http, u, fid, [free[0]])).json()
    r = await http.post("/v1/bookings", json={"flight_id": fid, "hold_id": h["hold_id"], "passengers": [{"name": "X", "seat_no": free[0]}]}, headers=u["h"])
    assert r.status_code == 400 and r.json()["error"] == "VALIDATION_ERROR"


async def test_my_bookings_lists_new_booking(http, users, make_flight):
    from .conftest import book, hold
    fid, free = await make_flight(2)
    (u,) = await users(1)
    h = (await hold(http, u, fid, [free[0]])).json()
    pnr = (await book(http, u, fid, h["hold_id"], [free[0]])).json()["pnr"]
    items = (await http.get("/v1/bookings", headers=u["h"])).json()["items"]
    assert [i["pnr"] for i in items] == [pnr] and items[0]["tickets"][0]["seat_no"] == free[0]


async def test_admin_endpoints(http):
    lg = await http.post("/v1/auth/login", json={"username": "Admin_Hamza", "password": "admin1234"})
    assert lg.status_code == 200 and lg.json()["is_admin"] is True
    h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
    d = await http.get("/v1/admin/dashboard", headers=h)
    assert d.status_code == 200 and "kpi" in d.json() and "top_routes" in d.json()      # degraded (no ClickHouse) still answers
    c = await http.get("/v1/admin/cluster", headers=h)
    assert c.status_code == 200 and "services" in c.json()
    assert (await http.post("/v1/admin/simulate/rm-rf", headers=h)).status_code == 400   # whitelist only
    assert (await http.get("/v1/admin/dashboard")).status_code == 401
