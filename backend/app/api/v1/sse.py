# backend/app/api/v1/sse.py
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.events import broadcaster

router = APIRouter()


async def _event_stream() -> AsyncGenerator[dict, None]:
    queue = await broadcaster.connect()
    try:
        while True:
            payload = await queue.get()
            yield {"event": payload["event"], "data": json.dumps(payload["data"])}
    finally:
        broadcaster.disconnect(queue)


@router.get("/ws/events", summary="SSE event stream")
async def sse_events() -> EventSourceResponse:
    return EventSourceResponse(_event_stream())
