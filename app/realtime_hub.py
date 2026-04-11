from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from fastapi import WebSocketDisconnect


class RealtimeHub:
    """Manage websocket clients and broadcast realtime detections; example: hub = RealtimeHub()."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock: asyncio.Lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Assign main event loop for publishing from worker threads; example: hub.set_event_loop(asyncio.get_running_loop())."""

        self._loop = loop

    async def websocket_handler(self, websocket: WebSocket) -> None:
        """Accept websocket connection and keep it alive; example: await hub.websocket_handler(websocket)."""

        await websocket.accept()
        async with self._clients_lock:
            self._clients.add(websocket)

        try:
            while True:
                # Frontend does not need to send data, but we still read to detect disconnects.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            async with self._clients_lock:
                if websocket in self._clients:
                    self._clients.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast payload to all connected frontend clients; example: await hub.broadcast({...})."""

        async with self._clients_lock:
            clients = list(self._clients)

        if len(clients) == 0:
            return

        disconnected_clients: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except RuntimeError:
                disconnected_clients.append(client)

        if len(disconnected_clients) > 0:
            async with self._clients_lock:
                for disconnected_client in disconnected_clients:
                    if disconnected_client in self._clients:
                        self._clients.remove(disconnected_client)

    def broadcast_from_thread(self, payload: dict[str, Any]) -> None:
        """Push payload from video/stream/webcam worker thread to main loop; example: hub.broadcast_from_thread({...})."""

        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)
