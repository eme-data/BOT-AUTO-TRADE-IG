from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from bot.config import settings
from dashboard.api.auth.jwt import ALGORITHM
from dashboard.api.deps import get_redis

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}
        self._counter = 0

    async def connect(self, ws: WebSocket) -> str:
        await ws.accept()
        self._counter += 1
        client_id = f"client_{self._counter}"
        self.active[client_id] = ws
        return client_id

    def disconnect(self, client_id: str) -> None:
        self.active.pop(client_id, None)

    async def broadcast(self, data: str) -> None:
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)


manager = ConnectionManager()


def _validate_ws_token(token: str | None) -> bool:
    """Validate JWT token for WebSocket connections."""
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.dashboard.secret_key, algorithms=[ALGORITHM])
        return payload.get("sub") is not None
    except JWTError:
        return False


@router.websocket("/ws/live")
async def websocket_live(ws: WebSocket, token: str | None = Query(default=None)):
    """WebSocket endpoint for real-time updates from Redis pub/sub.

    Requires JWT token as query parameter: /ws/live?token=<jwt>
    """
    if not _validate_ws_token(token):
        await ws.close(code=4001, reason="Unauthorized")
        return

    client_id = await manager.connect(ws)

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("bot:ticks", "bot:trades", "bot:positions", "bot:account", "bot:status", "bot:logs")

    async def redis_listener():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])

    listener_task = asyncio.create_task(redis_listener())

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        await pubsub.unsubscribe()
        manager.disconnect(client_id)
