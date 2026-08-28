import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.security import decode_access_token

logger = logging.getLogger("cctv.ws")

router = APIRouter(tags=["ws"])

broadcast_queue: asyncio.Queue = asyncio.Queue()


class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        # Iterate a snapshot, not the live set: a client connecting mid-broadcast
        # (manager.connect adds to self.active while this coroutine is suspended
        # on `await ws.send_json`) would otherwise raise "Set changed size during
        # iteration" and permanently kill fanout_loop's task.
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, token: str | None = None):
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket)
    try:
        while True:
            # Client doesn't need to send anything; just keep the connection open.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def fanout_loop():
    while True:
        event = await broadcast_queue.get()
        try:
            await manager.broadcast(event)
        except Exception:
            # Never let one bad broadcast permanently kill the fanout task --
            # every live-updating view (Dashboard, IncidentDetail) depends on
            # this loop staying alive for the rest of the process lifetime.
            logger.exception("fanout_loop failed to broadcast event: %s", event.get("type"))
