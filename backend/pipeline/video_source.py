"""
backend/pipeline/video_source.py

VideoSource owns one OpenCV capture (MP4 path, webcam int, or RTSP URL).
It runs a dedicated reader thread that keeps the latest frame fresh.
Thread-safe: callers use get_frame() / get_annotated_frame().
"""
import cv2
import threading
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


class SourceState(str, Enum):
    IDLE = "idle"           # created, not started
    ACTIVE = "active"       # reading frames normally
    OFFLINE = "offline"     # cap.read() failed / source unreachable
    FROZEN = "frozen"       # frames arriving but pixel-identical (camera tamper)
    BLACKOUT = "blackout"   # frame is nearly all black (lens blocked)
    STOPPED = "stopped"     # explicitly stopped


class VideoSource:
    """
    Manages a single video source.

    Usage:
        src = VideoSource(camera_id=1, source_uri="test.mp4")
        src.start()
        frame = src.get_frame()
        src.stop()
    """

    BLACKOUT_THRESHOLD = 10       # mean pixel value below this = blackout
    FREEZE_DIFF_THRESHOLD = 0.5   # mean abs diff below this = frozen
    FREEZE_CONSECUTIVE = 30       # frames in a row to declare frozen

    def __init__(self, camera_id: int, source_uri: str):
        self.camera_id = camera_id
        self.source_uri = source_uri

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._raw_frame: Optional[np.ndarray] = None          # latest decoded frame
        self._annotated_frame: Optional[np.ndarray] = None    # latest annotated frame (set by pipeline)

        self.state = SourceState.IDLE
        self._running = False

        self._last_frame_time: Optional[datetime] = None
        self._consecutive_frozen = 0
        self._prev_gray: Optional[np.ndarray] = None

        # stats exposed to API
        self.fps_actual: float = 0.0
        self._frame_count: int = 0
        self._fps_ts: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open capture and start reader thread. Returns True on success."""
        if self._running:
            return True

        # Resolve source: integer index for webcam, else string path/URL
        uri: any = self.source_uri
        try:
            uri = int(self.source_uri)
        except (ValueError, TypeError):
            pass

        self._cap = cv2.VideoCapture(uri)
        if not self._cap.isOpened():
            logger.error("Camera %d: failed to open source '%s'", self.camera_id, self.source_uri)
            self.state = SourceState.OFFLINE
            return False

        self._running = True
        self.state = SourceState.ACTIVE
        self._fps_ts = time.monotonic()

        self._thread = threading.Thread(
            target=self._reader_loop,
            name=f"vsrc-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Camera %d started (%s)", self.camera_id, self.source_uri)
        return True

    def stop(self):
        """Stop reader thread and release capture."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
            self._cap = None
        self.state = SourceState.STOPPED
        logger.info("Camera %d stopped", self.camera_id)

    # ── Frame access ─────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """Return latest raw frame (copy), or None if not available."""
        with self._lock:
            return self._raw_frame.copy() if self._raw_frame is not None else None

    def set_annotated_frame(self, frame: np.ndarray):
        """Called by DetectionPipeline to store the annotated frame."""
        with self._lock:
            self._annotated_frame = frame.copy()

    def get_annotated_frame(self) -> Optional[np.ndarray]:
        """Return latest annotated frame for MJPEG streaming."""
        with self._lock:
            if self._annotated_frame is not None:
                return self._annotated_frame.copy()
            # Fall back to raw if pipeline hasn't annotated yet
            return self._raw_frame.copy() if self._raw_frame is not None else None

    # ── Reader loop ──────────────────────────────────────────────────────────

    def _reader_loop(self):
        while self._running:
            ret, frame = self._cap.read()

            if not ret:
                # MP4: rewind; live source: mark offline
                if isinstance(self.source_uri, str) and self.source_uri.endswith((".mp4", ".avi", ".mov")):
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning("Camera %d: read failed — marking offline", self.camera_id)
                    self.state = SourceState.OFFLINE
                    time.sleep(2)
                    continue

            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            health = self._assess_health(frame)

            with self._lock:
                self._raw_frame = frame
                self.state = health
                self._last_frame_time = datetime.utcnow()

            self._update_fps()
            time.sleep(0.033)   # ~30 fps cap

    def _assess_health(self, frame: np.ndarray) -> SourceState:
        """Check for blackout or freeze. Returns appropriate SourceState."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Blackout: mean brightness below threshold
        if gray.mean() < self.BLACKOUT_THRESHOLD:
            self._consecutive_frozen = 0
            self._prev_gray = None
            return SourceState.BLACKOUT

        # Freeze: pixel diff vs previous frame nearly zero
        if self._prev_gray is not None:
            diff = np.abs(gray.astype(np.float32) - self._prev_gray.astype(np.float32)).mean()
            if diff < self.FREEZE_DIFF_THRESHOLD:
                self._consecutive_frozen += 1
                if self._consecutive_frozen >= self.FREEZE_CONSECUTIVE:
                    self._prev_gray = gray
                    return SourceState.FROZEN
            else:
                self._consecutive_frozen = 0

        self._prev_gray = gray
        return SourceState.ACTIVE

    def _update_fps(self):
        self._frame_count += 1
        now = time.monotonic()
        elapsed = now - self._fps_ts
        if elapsed >= 2.0:
            self.fps_actual = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_ts = now

    # ── Status dict ──────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "source_uri": self.source_uri,
            "state": self.state.value,
            "fps": round(self.fps_actual, 1),
            "last_frame": self._last_frame_time.isoformat() if self._last_frame_time else None,
        }
