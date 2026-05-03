# backend/app/core/events.py
import asyncio
import threading


class EventBroadcaster:
    def __init__(self) -> None:
        self._queues: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()

    async def connect(self) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._queues.append((loop, queue))
        return queue

    def disconnect(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._queues = [(loop, q) for loop, q in self._queues if q is not queue]

    def broadcast(self, event_type: str, data: dict) -> None:
        event = {"event": event_type, "data": data}
        with self._lock:
            queues = list(self._queues)
        for loop, queue in queues:
            loop.call_soon_threadsafe(queue.put_nowait, event)


broadcaster = EventBroadcaster()
