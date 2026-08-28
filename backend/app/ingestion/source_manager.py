"""Per-camera capture thread: reconnect-with-backoff, rolling buffer,
throttled person detection + tracking, zone-rule evaluation, and camera
health checks. One CameraWorker per Camera row; SourceManager owns them all.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone

import cv2
from sqlalchemy import and_, or_

from app.config import (
    DETECTION_TARGET_FPS,
    OFFLINE_TIMEOUT_SECONDS,
    ROLLING_BUFFER_SECONDS,
    STREAM_TARGET_FPS,
)
from app.db import SessionLocal
from app.detection.abandoned_object import AbandonedObjectHeuristic
from app.detection.camera_health import CameraHealthMonitor
from app.detection.centroid_tracker import CentroidTracker
from app.detection.fall_heuristic import FallHeuristic
from app.detection.fire_smoke_heuristic import FireSmokeHeuristic
from app.detection.person_tracker import detect_persons
from app.detection.schedule_eval import is_after_hours
from app.detection.zone_rules import ZoneDef, ZoneRuleEngine
from app.ingestion.event_bus import event_bus
from app.ingestion.rolling_buffer import RollingBuffer
from app.models import Camera, Schedule, Zone

logger = logging.getLogger("cctv.ingestion")

STREAM_WIDTH = 640
CONFIG_RELOAD_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 10.0

_STATUS_COLORS = {
    "restricted_entry": (0, 0, 220),
    "after_hours": (0, 140, 255),
    "loitering": (0, 200, 255),
    "presence": (60, 200, 60),
    "fall_warning": (0, 165, 255),
}

_SCENE_WARNING_COLORS = {
    "abandoned_object": (255, 140, 0),
    "fire_smoke": (0, 60, 255),
}

_SCENE_WARNING_LABELS = {
    "abandoned_object": "possible abandoned object",
    "fire_smoke": "possible fire/smoke - verify",
}


def _load_zone_defs(camera_id: str) -> list[ZoneDef]:
    db = SessionLocal()
    try:
        zones = db.query(Zone).filter(Zone.camera_id == camera_id).all()
        zone_ids = [z.id for z in zones]

        # One query for every relevant Schedule row instead of up to 2 queries
        # per zone (this runs every CONFIG_RELOAD_SECONDS per camera worker).
        schedules = db.query(Schedule).filter(
            or_(
                and_(Schedule.scope == "zone", Schedule.scope_id.in_(zone_ids)),
                and_(Schedule.scope == "camera", Schedule.scope_id == camera_id),
            )
        ).all() if zone_ids else []
        zone_schedules = {s.scope_id: s for s in schedules if s.scope == "zone"}
        camera_schedule = next((s for s in schedules if s.scope == "camera"), None)

        defs = []
        now = datetime.now()
        for z in zones:
            sched = zone_schedules.get(z.id) or camera_schedule
            # A Schedule row with an empty business_hours dict legitimately means
            # "closed every day" (see schedule_eval.is_after_hours's docstring),
            # which must still be evaluated -- `if hours else False` would treat
            # that falsy-but-present {} the same as "no schedule configured" and
            # silently force after_hours=False regardless.
            hours = json.loads(sched.business_hours_json) if sched else None
            after_hours = is_after_hours(hours, now) if hours is not None else False
            defs.append(ZoneDef(
                id=z.id,
                name=z.name,
                polygon=json.loads(z.polygon_json),
                restricted=z.restricted,
                loitering_threshold_s=z.loitering_threshold_s,
                after_hours_monitored=z.after_hours_monitored,
                is_after_hours=after_hours,
            ))
        return defs
    finally:
        db.close()


class CameraRuntimeState:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.status = "starting"
        self.active_tracks: dict = {}

    def set_frame(self, jpeg_bytes: bytes):
        with self.lock:
            self.latest_jpeg = jpeg_bytes

    def get_frame(self) -> bytes | None:
        with self.lock:
            return self.latest_jpeg


class CameraWorker(threading.Thread):
    def __init__(self, camera_id: str, name: str, source_type: str, uri: str, loop_video: bool):
        super().__init__(daemon=True, name=f"camera-{name}")
        self.camera_id = camera_id
        self.camera_name = name
        self.source_type = source_type
        self.uri = uri
        self.loop_video = loop_video

        self.state = CameraRuntimeState()
        self.buffer = RollingBuffer(ROLLING_BUFFER_SECONDS)
        self.tracker = CentroidTracker()
        self.rule_engine = ZoneRuleEngine()
        self.health = CameraHealthMonitor()
        self.fall_heuristic = FallHeuristic()
        self.abandoned_object = AbandonedObjectHeuristic()
        self.fire_smoke = FireSmokeHeuristic()

        self._stop_event = threading.Event()
        self._zones: list[ZoneDef] = []
        self._last_config_reload = 0.0
        self._last_detection = 0.0
        self._last_frame_ok_at: float | None = None
        self._consecutive_failures = 0
        self._reported_status = None
        self._start_time = time.time()

    def stop(self):
        self._stop_event.set()

    def run(self):
        detection_interval = 1.0 / DETECTION_TARGET_FPS
        stream_interval = 1.0 / STREAM_TARGET_FPS
        backoff = 1.0

        while not self._stop_event.is_set():
            cap = self._open_capture()
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()  # a non-None handle that failed to open still holds an OS resource
                self._report_failure()
                if self._stop_event.wait(backoff):
                    break
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue

            backoff = 1.0
            self._consecutive_failures = 0
            logger.info("Camera '%s' connected (%s)", self.camera_name, self.source_type)

            mid_stream_failures = 0

            while not self._stop_event.is_set():
                loop_start = time.time()
                ok, frame = cap.read()
                if not ok:
                    if self.source_type == "mp4":
                        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
                        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                        at_genuine_eof = total <= 0 or pos >= total - 1
                        if at_genuine_eof:
                            mid_stream_failures = 0
                            if self.loop_video:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                continue
                            else:
                                self._report_status("offline")
                                cap.release()
                                return
                        # transient mid-stream decode hiccup (e.g. under heavy system
                        # load) -- do NOT rewind to 0, that would repeatedly replay
                        # the opening frames and look like a frozen feed. Retry a
                        # few times in place before falling through to a full
                        # reconnect.
                        mid_stream_failures += 1
                        if mid_stream_failures <= 10:
                            time.sleep(0.05)
                            continue
                    break  # webcam/rtsp read failure, or repeated mp4 hiccups -> reconnect

                now = time.time()
                self._last_frame_ok_at = now
                self._consecutive_failures = 0
                mid_stream_failures = 0

                if now - self._last_config_reload > CONFIG_RELOAD_SECONDS:
                    self._zones = _load_zone_defs(self.camera_id)
                    self._last_config_reload = now

                h, w = frame.shape[:2]
                if w > STREAM_WIDTH:
                    scale = STREAM_WIDTH / w
                    frame = cv2.resize(frame, (STREAM_WIDTH, int(h * scale)))

                health = self.health.observe(frame)
                status = self._status_from_health(health)

                tracks = {}
                events = []
                scene_warnings = []
                if now - self._last_detection >= detection_interval:
                    self._last_detection = now
                    detections = detect_persons(frame)
                    person_bboxes = [d["bbox"] for d in detections]
                    tracks = self.tracker.update(person_bboxes, now)
                    conf_by_bbox = {tuple(d["bbox"]): d["confidence"] for d in detections}
                    events = self.rule_engine.evaluate(tracks, self._zones, now)
                    fall_events = self.fall_heuristic.evaluate(tracks, now)
                    for ev in fall_events:
                        ev["zone_id"] = self._zone_for_bbox(ev["bbox"])
                    events += fall_events
                    self.state.active_tracks = tracks
                    # events without an "emit" key (zone-rule events) always publish --
                    # they have their own per-(track,zone,type) cooldown built into
                    # ZoneRuleEngine and never repeat mid-cooldown in the first place.
                    # fall_events set "emit" explicitly: they're returned every tick
                    # once sustained (so the live-feed overlay box stays visible the
                    # whole time), but only publish a new Observation when emit=True.
                    for ev in events:
                        if not ev.get("emit", True):
                            continue
                        conf = ev.get("confidence", conf_by_bbox.get(tuple(ev["bbox"]), 0.5))
                        event_bus.publish({
                            "type": "observation",
                            "camera_id": self.camera_id,
                            "zone_id": ev.get("zone_id"),
                            "track_id": ev["track_id"],
                            "bbox": ev["bbox"],
                            "event_type": ev["event_type"],
                            "confidence": conf,
                        })

                    scene_warnings = self.abandoned_object.evaluate(frame, person_bboxes, now)
                    scene_warnings += self.fire_smoke.evaluate(frame, now)
                    for warn in scene_warnings:
                        if not warn.get("emit", True):
                            continue
                        event_bus.publish({
                            "type": "scene_warning",
                            "camera_id": self.camera_id,
                            "zone_id": self._zone_for_bbox(warn["bbox"]),
                            "bbox": warn["bbox"],
                            "warning_type": warn["warning_type"],
                            "confidence": warn["confidence"],
                        })
                else:
                    tracks = self.state.active_tracks

                annotated = self._annotate(frame, tracks, events, scene_warnings)
                ok_enc, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok_enc:
                    jpeg_bytes = buf.tobytes()
                    self.state.set_frame(jpeg_bytes)
                    bboxes = [info["bbox"] for info in tracks.values()]
                    self.buffer.add(jpeg_bytes, now, bboxes)

                self._report_status(status)

                elapsed = time.time() - loop_start
                if elapsed < stream_interval:
                    time.sleep(stream_interval - elapsed)

            cap.release()
            if self._stop_event.is_set():
                break

        logger.info("Camera '%s' worker stopped", self.camera_name)

    def _open_capture(self):
        try:
            if self.source_type == "webcam":
                index = int(self.uri) if self.uri.strip().isdigit() else 0
                return cv2.VideoCapture(index)
            return cv2.VideoCapture(self.uri)
        except Exception:
            logger.exception("Camera '%s' failed to open source", self.camera_name)
            return None

    def _report_failure(self):
        self._consecutive_failures += 1
        baseline = self._last_frame_ok_at or self._start_time
        offline = (time.time() - baseline) > OFFLINE_TIMEOUT_SECONDS
        self._report_status("offline" if offline else "starting")

    def _status_from_health(self, health: dict) -> str:
        if health["blackout"]:
            return "blackout"
        if health["frozen"]:
            return "frozen"
        if health["blurred"]:
            return "blurred"
        return "online"

    def _report_status(self, status: str):
        self.state.status = status
        if status == self._reported_status:
            return
        self._reported_status = status
        event_bus.publish({
            "type": "camera_status",
            "camera_id": self.camera_id,
            "status": status,
            "last_frame_at": self._last_frame_ok_at,
            "consecutive_failures": self._consecutive_failures,
        })

    def _annotate(self, frame, tracks: dict, events: list[dict], scene_warnings: list[dict] | None = None):
        annotated = frame.copy()
        h, w = annotated.shape[:2]
        flagged = {ev["track_id"]: ev["event_type"] for ev in events if ev["event_type"] != "presence"}
        for track_id, info in tracks.items():
            x1, y1, x2, y2 = info["bbox"]
            p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
            event_type = flagged.get(track_id, "presence")
            color = _STATUS_COLORS.get(event_type, (60, 200, 60))
            cv2.rectangle(annotated, p1, p2, color, 2)
            cv2.putText(annotated, f"#{track_id} {event_type}", (p1[0], max(0, p1[1] - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        for warn in scene_warnings or []:
            x1, y1, x2, y2 = warn["bbox"]
            p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
            color = _SCENE_WARNING_COLORS.get(warn["warning_type"], (200, 200, 200))
            label = _SCENE_WARNING_LABELS.get(warn["warning_type"], warn["warning_type"])
            cv2.rectangle(annotated, p1, p2, color, 2)
            cv2.putText(annotated, label, (p1[0], max(0, p1[1] - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        return annotated

    def _zone_for_bbox(self, bbox: list[float]) -> str | None:
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        for zone in self._zones:
            if zone.contains(cx, cy):
                return zone.id
        return None


class SourceManager:
    def __init__(self):
        self.workers: dict[str, CameraWorker] = {}
        self._lock = threading.Lock()

    def start_all(self, cameras: list[Camera]):
        for cam in cameras:
            self.start_camera(cam)

    def start_camera(self, cam: Camera):
        with self._lock:
            self.stop_camera(cam.id)
            worker = CameraWorker(cam.id, cam.name, cam.source_type, cam.uri, cam.loop)
            worker.start()
            self.workers[cam.id] = worker

    def stop_camera(self, camera_id: str):
        worker = self.workers.pop(camera_id, None)
        if worker:
            worker.stop()

    def stop_all(self):
        with self._lock:
            for worker in self.workers.values():
                worker.stop()
            for worker in self.workers.values():
                worker.join(timeout=3)
            self.workers.clear()

    def get_frame(self, camera_id: str) -> bytes | None:
        worker = self.workers.get(camera_id)
        return worker.state.get_frame() if worker else None

    def get_buffer(self, camera_id: str) -> RollingBuffer | None:
        worker = self.workers.get(camera_id)
        return worker.buffer if worker else None

    def get_frame_and_boxes(self, camera_id: str) -> tuple[bytes | None, list]:
        worker = self.workers.get(camera_id)
        if not worker:
            return None, []
        frame = worker.state.get_frame()
        boxes = [info["bbox"] for info in worker.state.active_tracks.values()]
        return frame, boxes


source_manager = SourceManager()
