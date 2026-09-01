"""
backend/pipeline/detection_pipeline.py

DetectionPipeline attaches to one VideoSource and runs the full
detection stack in a background thread:

  YOLO → CentroidTracker → ZoneAnalyzer → LineCounter → PostureClassifier
                                         ↓
                               write Observation rows
                                         ↓
                               push annotated frame → VideoSource

Privacy contract:
  - FaceProcessor is NOT used here. Face blurring is a display-layer concern
    handled by the MJPEG endpoint if enabled. No face data ever touches the DB.
  - track_id is camera-local and rotates each session (no cross-camera linkage).
"""
import json
import logging
import threading
import time
import hashlib
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from backend.db.database import SessionLocal
from backend.db.models import Camera, Observation, Zone
from backend.modules.centroid_tracker import CentroidTracker
from backend.modules.zone_analyzer import ZoneAnalyzer
from backend.modules.line_counter import LineCounter
from backend.modules.posture_classifier import PostureClassifier
from .video_source import VideoSource, SourceState, FRAME_WIDTH, FRAME_HEIGHT

logger = logging.getLogger(__name__)

# Lazy YOLO import — avoids loading torch at module import time
_yolo_model = None
_yolo_lock = threading.Lock()


def _get_yolo():
    global _yolo_model
    with _yolo_lock:
        if _yolo_model is None:
            try:
                import torch
                from ultralytics import YOLO
                _yolo_model = YOLO("yolov8n.pt")
                if torch.cuda.is_available():
                    _yolo_model.to("cuda")
                    logger.info("YOLO loaded on CUDA")
                else:
                    logger.info("YOLO loaded on CPU")
            except Exception as exc:
                logger.error("Failed to load YOLO: %s", exc)
        return _yolo_model


class DetectionPipeline:
    """
    Runs detection for one camera in a daemon thread.

    Instantiate → call start() → call stop() when done.
    """

    CONFIDENCE_THRESHOLD = 0.35
    LOITERING_SECONDS = 5            # stationary for 5s = loitering event
    RESTRICTED_IMPACT = 0.9
    AFTER_HOURS_IMPACT = 0.7
    LOITERING_IMPACT = 0.5

    def __init__(self, source: VideoSource, camera_db_id: int):
        self.source = source
        self.camera_db_id = camera_db_id

        self._tracker = CentroidTracker(max_disappeared=50, max_distance=120)
        self._zone_analyzer = ZoneAnalyzer(FRAME_WIDTH, FRAME_HEIGHT)
        self._posture = PostureClassifier()

        line_y = FRAME_HEIGHT // 2
        self._line_counter = LineCounter(
            (100, line_y), (FRAME_WIDTH - 100, line_y)
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # DB-loaded zone polygons: list of (Zone.id, np.array of points, zone_type)
        self._zones: list = []
        self._load_zones()

        # Schedules (after-hours detection)
        self._schedules: list = []
        self._load_schedules()

        # Dedup: track which (track_id, event_type) we already filed this session
        self._filed_events: set = set()

    # ── Startup / shutdown ───────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name=f"pipeline-{self.camera_db_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("DetectionPipeline started for camera %d", self.camera_db_id)

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("DetectionPipeline stopped for camera %d", self.camera_db_id)

    # ── Main loop ────────────────────────────────────────────────────────────

    def _loop(self):
        yolo = _get_yolo()
        consecutive_errors = 0

        while self._running:
            if self.source.state == SourceState.STOPPED:
                break

            # Health anomaly events (offline / frozen / blackout)
            if self.source.state in (SourceState.OFFLINE, SourceState.FROZEN, SourceState.BLACKOUT):
                event_map = {
                    SourceState.OFFLINE: "camera_offline",
                    SourceState.FROZEN: "camera_frozen",
                    SourceState.BLACKOUT: "camera_blackout",
                }
                self._write_observation(
                    track_id="system",
                    event_type=event_map[self.source.state],
                    zone_id=None,
                    confidence=1.0,
                    impact=1.0,
                    explanation=f"Camera health anomaly: {self.source.state.value}",
                    metadata={},
                )
                time.sleep(10)   # don't spam DB on sustained anomaly
                continue

            frame = self.source.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            try:
                annotated = self._process_frame(frame, yolo)
                self.source.set_annotated_frame(annotated)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                logger.error("Pipeline error cam %d: %s", self.camera_db_id, exc)
                if consecutive_errors > 10:
                    logger.critical("Pipeline cam %d: too many errors, stopping", self.camera_db_id)
                    break
                time.sleep(1)

    # ── Frame processing ─────────────────────────────────────────────────────

    def _process_frame(self, frame: np.ndarray, yolo) -> np.ndarray:
        annotated = frame.copy()
        timestamp = datetime.utcnow()
        is_after_hours = self._check_after_hours(timestamp)

        # ── YOLO detection ───────────────────────────────────────────────────
        person_boxes = []
        if yolo is not None:
            try:
                import supervision as sv
                results = yolo(frame, verbose=False)[0]
                detections = sv.Detections.from_ultralytics(results)
                mask = (detections.class_id == 0) & (detections.confidence > self.CONFIDENCE_THRESHOLD)
                person_detections = detections[mask]
                person_boxes = person_detections.xyxy.astype(int).tolist()
            except Exception as exc:
                logger.debug("YOLO inference error: %s", exc)

        # ── Tracker update ───────────────────────────────────────────────────
        objects_info = self._tracker.update(person_boxes)

        # ── Per-person analysis ───────────────────────────────────────────────
        for track_id_str, info in objects_info.items():
            centroid = info["centroid"]
            bbox = info["bbox"]
            x1, y1, x2, y2 = bbox

            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(annotated, (int(centroid[0]), int(centroid[1])), 5, (0, 255, 0), -1)
            cv2.putText(annotated, f"ID:{track_id_str}", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Posture label
            try:
                posture, _ = self._posture.classify_posture(frame, bbox)
                cv2.putText(annotated, posture, (x1, y2 + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            except Exception:
                pass

            # Zone hit check
            hit_zone_id, hit_zone_type = self._zone_hit(centroid)

            # Camera 3: No Entry Area — triggers restricted_zone_entry whenever person detected
            if self.camera_db_id == 3:
                self._maybe_file(
                    track_id=track_id_str,
                    event_type="restricted_zone_entry",
                    zone_id=hit_zone_id,
                    confidence=0.95,
                    impact=self.RESTRICTED_IMPACT,
                    explanation="NO ENTRY AREA BREACH: Person detected on Camera 3",
                    metadata={"centroid": centroid, "bbox": bbox, "frame_w": FRAME_WIDTH, "frame_h": FRAME_HEIGHT},
                )
                cv2.putText(annotated, "NO ENTRY AREA BREACH", (x1, y1 - 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Camera 1 & Camera 2: Loitering check
            elif self.camera_db_id in (1, 2):
                if info.get("is_stationary"):
                    last_seen = datetime.fromisoformat(info["last_seen"])
                    dwell = (timestamp - last_seen).total_seconds()
                    if dwell >= self.LOITERING_SECONDS:
                        self._maybe_file(
                            track_id=track_id_str,
                            event_type="loitering",
                            zone_id=hit_zone_id,
                            confidence=0.85,
                            impact=self.LOITERING_IMPACT,
                            explanation=f"Person stationary for {int(dwell)}s on Camera {self.camera_db_id}",
                            metadata={"dwell_seconds": int(dwell), "centroid": centroid},
                        )
                        cv2.putText(annotated, f"LOITER {int(dwell)}s",
                                    (int(centroid[0]) - 40, int(centroid[1]) + 35),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # ── Line counter ──────────────────────────────────────────────────────
        self._line_counter.update(objects_info)
        cv2.line(annotated, self._line_counter.line_start,
                 self._line_counter.line_end, (255, 255, 0), 2)

        # ── Zone overlay ──────────────────────────────────────────────────────
        for zone_id, pts, zone_type in self._zones:
            color = (0, 0, 200) if zone_type == "restricted" else (0, 200, 100)
            cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=2)

        # ── HUD ───────────────────────────────────────────────────────────────
        self._draw_hud(annotated, timestamp, len(objects_info), is_after_hours)

        return annotated

    # ── Zone / schedule helpers ───────────────────────────────────────────────

    def _zone_hit(self, centroid) -> tuple[Optional[int], Optional[str]]:
        """Return (zone_id, zone_type) if centroid is inside any loaded zone, else (None, None)."""
        pt = (float(centroid[0]), float(centroid[1]))
        for zone_id, pts, zone_type in self._zones:
            if cv2.pointPolygonTest(pts, pt, measureDist=False) >= 0:
                return zone_id, zone_type
        return None, None

    def _check_after_hours(self, ts: datetime) -> bool:
        """True if current time falls outside all schedules for this camera."""
        if not self._schedules:
            return False  # no schedule = always monitored, never after-hours
        current_day = ts.strftime("%a")  # Mon, Tue, …
        current_time = ts.strftime("%H:%M")
        for sched in self._schedules:
            days = json.loads(sched["days_of_week"])
            if current_day in days:
                if sched["start_time"] <= current_time <= sched["end_time"]:
                    return False  # inside a valid schedule window
        return True  # outside all windows

    def _load_zones(self):
        """Load polygon zones from DB for this camera."""
        try:
            db = SessionLocal()
            zones = db.query(Zone).filter(Zone.camera_id == self.camera_db_id).all()
            self._zones = [
                (
                    z.id,
                    np.array(json.loads(z.polygon_points), dtype=np.int32),
                    z.zone_type,
                )
                for z in zones
            ]
            db.close()
            logger.info("Camera %d: loaded %d zones", self.camera_db_id, len(self._zones))
        except Exception as exc:
            logger.error("Camera %d: failed to load zones: %s", self.camera_db_id, exc)

    def _load_schedules(self):
        """Load schedules from DB for this camera."""
        try:
            from backend.db.models import Schedule
            db = SessionLocal()
            scheds = db.query(Schedule).filter(Schedule.camera_id == self.camera_db_id).all()
            self._schedules = [
                {
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "days_of_week": s.days_of_week,
                }
                for s in scheds
            ]
            db.close()
        except Exception as exc:
            logger.error("Camera %d: failed to load schedules: %s", self.camera_db_id, exc)

    # ── DB write helpers ─────────────────────────────────────────────────────

    def _maybe_file(self, track_id: str, event_type: str, **kwargs):
        """
        Write an Observation only once per (track_id, event_type) per session.
        Loitering is re-filed every 60s after the first filing.
        """
        # Strict camera-specific alert filtering
        if self.camera_db_id in (1, 2) and event_type not in ("loitering", "camera_offline", "camera_frozen", "camera_blackout"):
            return
        if self.camera_db_id == 3 and event_type != "restricted_zone_entry":
            return

        key = f"{track_id}:{event_type}"
        if event_type == "loitering":
            # Re-file every 60 s
            ts_key = f"{key}:ts"
            last_filed = self._filed_events_ts().get(ts_key, 0)
            if time.monotonic() - last_filed < 60:
                return
            self._loiter_ts[ts_key] = time.monotonic()
        else:
            if key in self._filed_events:
                return
            self._filed_events.add(key)
        self._write_observation(track_id=track_id, event_type=event_type, **kwargs)

    # ugly but avoids extra class attr
    _loiter_ts: dict = {}

    def _filed_events_ts(self):
        return self._loiter_ts

    def _write_observation(
        self,
        track_id: str,
        event_type: str,
        zone_id: Optional[int],
        confidence: float,
        impact: float,
        explanation: str,
        metadata: dict,
    ):
        try:
            db = SessionLocal()
            obs = Observation(
                camera_id=self.camera_db_id,
                track_id=track_id,
                event_type=event_type,
                timestamp=datetime.utcnow(),
                zone_id=zone_id,
                confidence_score=round(min(max(confidence, 0.0), 1.0), 4),
                impact_score=round(min(max(impact, 0.0), 1.0), 4),
                explanation=explanation,
                raw_metadata=json.dumps(metadata) if metadata else None,
            )
            db.add(obs)
            db.commit()
            db.refresh(obs)

            cam = db.query(Camera).filter(Camera.id == self.camera_db_id).first()
            cam_name = cam.name if cam else f"Camera {self.camera_db_id}"

            alert_payload = {
                "id": obs.id,
                "camera_id": obs.camera_id,
                "camera_name": cam_name,
                "track_id": obs.track_id,
                "event_type": obs.event_type,
                "timestamp": obs.timestamp.isoformat(),
                "zone_id": obs.zone_id,
                "confidence_score": obs.confidence_score,
                "impact_score": obs.impact_score,
                "explanation": obs.explanation,
                "acknowledged": False,
            }
            try:
                from backend.alerts.alert_manager import get_alert_manager
                get_alert_manager().publish_alert(alert_payload)
            except Exception as broadcast_exc:
                logger.warning("Failed to broadcast alert payload: %s", broadcast_exc)

            logger.debug(
                "Observation written: cam=%d track=%s event=%s",
                self.camera_db_id, track_id, event_type,
            )
        except Exception as exc:
            logger.error("Failed to write observation: %s", exc)
        finally:
            db.close()

    # ── HUD overlay ──────────────────────────────────────────────────────────

    def _draw_hud(self, frame, ts: datetime, count: int, after_hours: bool):
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (8, h - 90), (360, h - 8), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        lines = [
            ts.strftime("%Y-%m-%d  %H:%M:%S UTC"),
            f"People: {count}   In:{self._line_counter.entry_count} Out:{self._line_counter.exit_count}",
            ("AFTER HOURS" if after_hours else "In-schedule"),
        ]
        colors = [(255, 255, 255), (255, 255, 255), (0, 80, 255) if after_hours else (100, 255, 100)]
        for i, (txt, col) in enumerate(zip(lines, colors)):
            cv2.putText(frame, txt, (14, h - 70 + i * 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
