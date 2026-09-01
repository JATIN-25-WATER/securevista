"""
tests/test_video_source.py
Unit tests for VideoSource — no real video file needed.
Uses mocked OpenCV capture.
"""
import time
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from backend.pipeline.video_source import VideoSource, SourceState, FRAME_WIDTH, FRAME_HEIGHT


def make_frame(brightness: int = 128) -> np.ndarray:
    """Return a solid-color BGR frame."""
    return np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), brightness, dtype=np.uint8)


@pytest.fixture
def mock_cap():
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.return_value = (True, make_frame(128))
    return cap


# ── Construction ─────────────────────────────────────────────────────────────

def test_initial_state():
    src = VideoSource(camera_id=42, source_uri="test.mp4")
    assert src.state == SourceState.IDLE
    assert src.camera_id == 42
    assert src.get_frame() is None


# ── start() / stop() ─────────────────────────────────────────────────────────

def test_start_success(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=1, source_uri="test.mp4")
        ok = src.start()
        assert ok
        assert src.state == SourceState.ACTIVE
        assert src._running
        src.stop()
        assert src.state == SourceState.STOPPED


def test_start_failure():
    bad_cap = MagicMock()
    bad_cap.isOpened.return_value = False
    with patch("cv2.VideoCapture", return_value=bad_cap):
        src = VideoSource(camera_id=2, source_uri="nonexistent.mp4")
        ok = src.start()
        assert not ok
        assert src.state == SourceState.OFFLINE


def test_double_start_noop(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=3, source_uri="test.mp4")
        ok1 = src.start()
        ok2 = src.start()   # should be noop
        assert ok1 and ok2
        src.stop()


# ── Health assessment ─────────────────────────────────────────────────────────

def test_assess_health_active():
    src = VideoSource(camera_id=10, source_uri="x")
    frame = make_frame(128)
    state = src._assess_health(frame)
    assert state == SourceState.ACTIVE


def test_assess_health_blackout():
    src = VideoSource(camera_id=11, source_uri="x")
    dark_frame = make_frame(3)   # well below threshold
    state = src._assess_health(dark_frame)
    assert state == SourceState.BLACKOUT


def test_assess_health_frozen():
    src = VideoSource(camera_id=12, source_uri="x")
    frame = make_frame(100)

    # Feed identical frames until FREEZE_CONSECUTIVE threshold
    for _ in range(VideoSource.FREEZE_CONSECUTIVE + 5):
        state = src._assess_health(frame)

    assert state == SourceState.FROZEN


def test_assess_health_no_freeze_on_motion():
    src = VideoSource(camera_id=13, source_uri="x")
    for i in range(40):
        # Alternate brightness to simulate motion
        frame = make_frame(100 + (i % 2) * 50)
        state = src._assess_health(frame)
    assert state != SourceState.FROZEN


# ── Annotated frame ──────────────────────────────────────────────────────────

def test_set_and_get_annotated_frame(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=20, source_uri="test.mp4")
        src.start()
        time.sleep(0.1)   # let reader thread tick at least once

        annotated = make_frame(200)
        src.set_annotated_frame(annotated)
        got = src.get_annotated_frame()
        assert got is not None
        assert got.shape == annotated.shape
        src.stop()


# ── Status dict ──────────────────────────────────────────────────────────────

def test_status_dict(mock_cap):
    with patch("cv2.VideoCapture", return_value=mock_cap):
        src = VideoSource(camera_id=30, source_uri="rtsp://cam")
        src.start()
        d = src.status_dict()
        assert d["camera_id"] == 30
        assert d["source_uri"] == "rtsp://cam"
        assert "state" in d
        assert "fps" in d
        src.stop()
