"""MongoDB (eventually consistent, loss-tolerant): search events, view counters, audit log. Never on the critical path."""
import asyncio
import logging
from typing import Any

log = logging.getLogger("ars")


def create_mongo(url: str):
    if not url:
        return None
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(url, serverSelectionTimeoutMS=800, connectTimeoutMS=800)


async def _insert(client: Any, coll: str, doc: dict) -> None:
    try:
        await client["ars"][coll].insert_one(doc)
    except Exception as e:  # noqa: BLE001
        log.debug("mongo insert failed: %s", e)


async def _inc_view(client: Any, flight_id: int) -> None:
    try:
        await client["ars"]["flight_views"].update_one({"_id": flight_id}, {"$inc": {"views": 1}}, upsert=True)
    except Exception as e:  # noqa: BLE001
        log.debug("mongo view inc failed: %s", e)


def fire_event(client: Any, coll: str, doc: dict) -> None:
    """Fire-and-forget: the request never waits on MongoDB."""
    if client is not None:
        asyncio.get_running_loop().create_task(_insert(client, coll, doc))


def fire_view(client: Any, flight_id: int) -> None:
    if client is not None:
        asyncio.get_running_loop().create_task(_inc_view(client, flight_id))
