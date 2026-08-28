"""Bridges camera-worker threads (plain Python threading) to the FastAPI
asyncio event loop: persists observations/camera-status to the DB on a
single writer thread (avoids SQLite write contention across camera
threads), then forwards the same event to any subscribed websockets."""
import asyncio
import json
import logging
import queue
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Camera, Observation, SceneWarning

logger = logging.getLogger("cctv.event_bus")


class EventBus:
    def __init__(self):
        self._queue: "queue.Queue[dict | None]" = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_queue: "asyncio.Queue | None" = None
        self._writer_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.on_observation = None  # set by incident engine once it's wired in
        self.on_camera_status = None
        self.on_scene_warning = None

    def publish(self, event: dict):
        self._queue.put(event)

    def bind_loop(self, loop: asyncio.AbstractEventLoop, broadcast_queue: asyncio.Queue):
        self._loop = loop
        self._broadcast_queue = broadcast_queue

    def start(self):
        self._stop.clear()
        self._writer_thread = threading.Thread(target=self._run, daemon=True, name="event-writer")
        self._writer_thread.start()

    def stop(self):
        self._stop.set()
        self._queue.put(None)
        if self._writer_thread:
            self._writer_thread.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            event = self._queue.get()
            if event is None:
                break
            try:
                self._handle(event)
            except Exception:
                logger.exception("event bus failed to handle event: %s", event.get("type"))

    def _handle(self, event: dict):
        etype = event["type"]
        db = SessionLocal()
        try:
            if etype == "observation":
                obs = Observation(
                    camera_id=event["camera_id"],
                    zone_id=event.get("zone_id"),
                    track_id=event["track_id"],
                    bbox_json=json.dumps(event["bbox"]),
                    event_type=event["event_type"],
                    confidence=event.get("confidence", 0.0),
                )
                db.add(obs)
                db.commit()
                db.refresh(obs)
                event["id"] = obs.id
                event["ts"] = obs.ts.isoformat()
                if self.on_observation:
                    self.on_observation(db, obs)
            elif etype == "camera_status":
                cam = db.query(Camera).filter(Camera.id == event["camera_id"]).first()
                if cam:
                    prev_status = cam.status
                    cam.status = event["status"]
                    if event.get("last_frame_at"):
                        cam.last_frame_at = datetime.fromtimestamp(event["last_frame_at"], tz=timezone.utc)
                    cam.consecutive_failures = event.get("consecutive_failures", cam.consecutive_failures)
                    db.commit()
                    if self.on_camera_status and prev_status != cam.status:
                        self.on_camera_status(db, cam, prev_status)
            elif etype == "scene_warning":
                warning = SceneWarning(
                    camera_id=event["camera_id"],
                    zone_id=event.get("zone_id"),
                    bbox_json=json.dumps(event["bbox"]),
                    warning_type=event["warning_type"],
                    confidence=event.get("confidence", 0.0),
                )
                db.add(warning)
                db.commit()
                db.refresh(warning)
                event["id"] = warning.id
                event["ts"] = warning.ts.isoformat()
                if self.on_scene_warning:
                    self.on_scene_warning(db, warning)
        finally:
            db.close()
        self._forward_to_websockets(event)

    def _forward_to_websockets(self, event: dict):
        if self._loop and self._broadcast_queue:
            self._loop.call_soon_threadsafe(self._broadcast_queue.put_nowait, event)


event_bus = EventBus()
