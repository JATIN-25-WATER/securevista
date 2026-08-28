"""Fire/smoke visual heuristic: an HSV color-range + sustained-area check.
This is explicitly the LEAST reliable heuristic in the system -- it is not
a trained classifier, cannot distinguish real flame from any other
orange/red bright object (a jacket, a traffic cone, sunset glare through a
window), and is scored with the lowest confidence cap of any incident type
(see incident/scoring.py). It exists purely as a visual cue for a human to
check, never as a standalone automatic alarm.
"""
import cv2
import numpy as np

FLAME_HSV_LOWER = np.array([5, 80, 150], dtype=np.uint8)  # orange/red-ish, bright
FLAME_HSV_UPPER = np.array([30, 255, 255], dtype=np.uint8)
MIN_AREA_FRACTION = 0.01
SUSTAIN_SECONDS = 6.0
COOLDOWN_SECONDS = 45.0


class FireSmokeHeuristic:
    """One instance per camera."""

    def __init__(self):
        self._flagged_since: float | None = None
        self._last_emitted: float | None = None

    def evaluate(self, frame, now_ts: float) -> list[dict]:
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, FLAME_HSV_LOWER, FLAME_HSV_UPPER)
        area_fraction = float(np.count_nonzero(mask)) / (h * w)

        if area_fraction < MIN_AREA_FRACTION:
            self._flagged_since = None
            return []

        if self._flagged_since is None:
            self._flagged_since = now_ts
        dwell = now_ts - self._flagged_since
        if dwell < SUSTAIN_SECONDS:
            return []

        should_emit = self._last_emitted is None or (now_ts - self._last_emitted) >= COOLDOWN_SECONDS
        if should_emit:
            self._last_emitted = now_ts

        # Returned every tick once sustained (not just on the cooldown-gated
        # emission) so the live-feed overlay box stays visible the whole time.
        ys, xs = np.nonzero(mask)
        bbox = [float(xs.min()) / w, float(ys.min()) / h, float(xs.max()) / w, float(ys.max()) / h]
        confidence = min(0.3, 0.1 + area_fraction)  # deliberately capped very low
        return [{
            "bbox": bbox,
            "warning_type": "fire_smoke",
            "dwell_seconds": dwell,
            "confidence": confidence,
            "emit": should_emit,
        }]
