"""
backend/alerts/alert_manager.py

Singleton manager for real-time WebSocket security alert broadcasting.
Handles client connection lifecycle and thread-safe alert dispatching
from detection background threads to active WebSocket subscribers.
"""
import asyncio
import logging
from typing import Set, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AlertManager:
    _instance = None

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop = None

    @classmethod
    def get_instance(cls) -> "AlertManager":
        if cls._instance is None:
            cls._instance = AlertManager()
        return cls._instance

    def register_loop(self, loop: asyncio.AbstractEventLoop):
        """Register the main FastAPI event loop."""
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, payload: Dict[str, Any]):
        """Broadcast a message payload to all connected clients asynchronously."""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception as exc:
                logger.warning(f"Error sending message to client: {exc}")
                disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def publish_alert(self, alert_data: Dict[str, Any]):
        """
        Thread-safe method to publish a new detection alert.
        Can be called safely from background pipeline threads.
        Automatically dispatches Telegram notification to the dedicated bot.
        """
        message = {
            "type": "NEW_ALERT",
            "data": alert_data
        }
        self._dispatch(message)

        # Dispatch to dedicated Telegram bot (non-blocking)
        try:
            from backend.services.telegram_service import get_telegram_notifier
            get_telegram_notifier().send_alert_notification(alert_data)
        except Exception as exc:
            logger.warning(f"Failed to trigger Telegram notification: {exc}")

    def publish_ack(self, ack_data: Dict[str, Any]):
        """
        Thread-safe method to publish an alert acknowledgement update.
        """
        message = {
            "type": "ALERT_ACKNOWLEDGED",
            "data": ack_data
        }
        self._dispatch(message)

    def _dispatch(self, message: Dict[str, Any]):
        """Dispatch message to the asyncio event loop."""
        try:
            loop = self._loop
            if loop is None or not loop.is_running():
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
            else:
                logger.warning("No running asyncio event loop available for AlertManager broadcast.")
        except Exception as exc:
            logger.error(f"Failed to dispatch alert: {exc}")


def get_alert_manager() -> AlertManager:
    return AlertManager.get_instance()
