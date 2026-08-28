"""Camera health signals: frozen feed, covered/blackout, severe blur.
Offline detection itself lives in ingestion/source_manager.py (it's a
function of read-failures over time, not frame content)."""
import logging
import time
from collections import deque

import cv2
import numpy as np

from app.config import (
    BLACKOUT_BRIGHTNESS_THRESHOLD,
    BLACKOUT_STD_THRESHOLD,
    BLUR_LAPLACIAN_THRESHOLD,
    FROZEN_DIFF_THRESHOLD,
    FROZEN_WINDOW_SECONDS,
)

MIN_SAMPLES_FOR_FROZEN_VERDICT = 5
logger = logging.getLogger("cctv.health.debug")


class CameraHealthMonitor:
    """One instance per camera. Feed it frames as they're captured; call
    observe() to get the current health verdict. The frozen-feed check is
    time-bounded (FROZEN_WINDOW_SECONDS), not frame-count-bounded, so it
    isn't fooled by a fast capture rate feeding it many near-duplicate
    frames within a fraction of a second."""

    def __init__(self):
        # Unbounded on purpose: eviction is time-based (see the cutoff loop in
        # observe()), not count-based. A fixed maxlen here would silently
        # evict samples before that time-based prune ever runs whenever the
        # capture rate is fast enough to fill it in under FROZEN_WINDOW_SECONDS
        # (true for most local mp4/webcam sources decoding faster than 256
        # frames / (0.8 * FROZEN_WINDOW_SECONDS)), permanently preventing the
        # frozen-feed verdict from ever firing.
        self.recent_frames: deque = deque()  # (wall_time, small_gray_frame)

    def observe(self, frame) -> dict:
        now = time.time()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        self.recent_frames.append((now, small))
        cutoff = now - FROZEN_WINDOW_SECONDS
        while self.recent_frames and self.recent_frames[0][0] < cutoff:
            self.recent_frames.popleft()

        brightness = float(np.mean(small))
        stddev = float(np.std(small))
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        blackout = brightness < BLACKOUT_BRIGHTNESS_THRESHOLD or stddev < BLACKOUT_STD_THRESHOLD
        frozen = self._is_frozen()
        blurred = (not blackout) and laplacian_var < BLUR_LAPLACIAN_THRESHOLD

        return {
            "blackout": blackout,
            "frozen": frozen,
            "blurred": blurred,
            "brightness": brightness,
            "stddev": stddev,
            "laplacian_var": laplacian_var,
        }

    def _is_frozen(self) -> bool:
        samples = list(self.recent_frames)
        if len(samples) < MIN_SAMPLES_FOR_FROZEN_VERDICT:
            return False
        span = samples[-1][0] - samples[0][0]
        if span < FROZEN_WINDOW_SECONDS * 0.8:
            return False  # haven't actually observed a full window yet
        frames = [s[1] for s in samples]
        diffs = [float(np.mean(cv2.absdiff(frames[i], frames[i + 1]))) for i in range(len(frames) - 1)]
        result = max(diffs) < FROZEN_DIFF_THRESHOLD
        if result:
            logger.warning(
                "FROZEN verdict: %d samples span=%.2fs max_diff=%.4f diffs=%s",
                len(samples), span, max(diffs), [round(d, 3) for d in diffs],
            )
        return result
