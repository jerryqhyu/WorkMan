from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class EventBroker:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()
        self._websockets: set[WebSocket] = set()

    async def publish(self, event: dict[str, Any]) -> None:
        dead_queues: list[asyncio.Queue] = []
        for queue in self._queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)
        for queue in dead_queues:
            self._queues.discard(queue)
        dead_ws: list[WebSocket] = []
        for websocket in self._websockets:
            try:
                await websocket.send_json(event)
            except Exception:
                dead_ws.append(websocket)
        for websocket in dead_ws:
            self._websockets.discard(websocket)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def connect_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._websockets.add(websocket)

    def disconnect_websocket(self, websocket: WebSocket) -> None:
        self._websockets.discard(websocket)


broker = EventBroker()
