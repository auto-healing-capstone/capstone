# backend/app/core/events.py
import asyncio


class EventBroadcaster:
    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    async def connect(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue) -> None:
        self._queues.remove(queue)

    def broadcast(self, event_type: str, data: dict) -> None:
        for queue in list(self._queues):
            queue.put_nowait({"event": event_type, "data": data})


broadcaster = EventBroadcaster()
