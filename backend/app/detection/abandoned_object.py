"""Abandoned-object heuristic: classic background subtraction + static-blob
timing. This does NOT classify what the object is (a bag, a box, trash) --
it only knows a new foreground blob appeared, does not overlap any tracked
person, and has stayed essentially motionless for a sustained period. Scored
and worded as a low/medium-confidence warning, never a confident claim.

Unlike detection/zone_rules.py and detection/fall_heuristic.py, this reads
raw frame pixels (for the background model), not just bbox geometry, so it
is exercised via live/staged video rather than the deterministic bbox-only
scenario-replay harness.
"""
import uuid

import cv2
import numpy as np

MIN_CONTOUR_AREA_FRACTION = 0.0015  # relative to frame area
STATIC_IOU_THRESHOLD = 0.6  # overlap with its previous position required to count as "the same still blob"
PERSON_OVERLAP_IOU_THRESHOLD = 0.05  # any overlap with a tracked person above this excludes the blob
ABANDONED_SUSTAIN_SECONDS = 15.0
COOLDOWN_SECONDS = 30.0


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class AbandonedObjectHeuristic:
    """One instance per camera."""

    def __init__(self):
        self._subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32, detectShadows=False)
        self._candidates: dict[str, dict] = {}  # blob_id -> {bbox, first_seen}
        self._last_emitted: dict[str, float] = {}

    def evaluate(self, frame, person_bboxes: list[list[float]], now_ts: float) -> list[dict]:
        h, w = frame.shape[:2]
        fg_mask = self._subtractor.apply(frame)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = MIN_CONTOUR_AREA_FRACTION * (h * w)
        blobs = []
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            bbox = [x / w, y / h, (x + bw) / w, (y + bh) / h]
            if any(_iou(bbox, p) > PERSON_OVERLAP_IOU_THRESHOLD for p in person_bboxes):
                continue
            blobs.append(bbox)

        seen_ids: set[str] = set()
        for bbox in blobs:
            # Best IoU match among candidates not already claimed this tick --
            # not just the first one above threshold, and never the same
            # candidate twice, so two distinct static objects that both
            # happen to overlap one old candidate don't silently merge into
            # a single tracked blob (only one of them would ever be reported).
            best_id, best_iou = None, 0.0
            for cid, cand in self._candidates.items():
                if cid in seen_ids:
                    continue
                iou = _iou(bbox, cand["bbox"])
                if iou >= STATIC_IOU_THRESHOLD and iou > best_iou:
                    best_id, best_iou = cid, iou
            if best_id is None:
                best_id = uuid.uuid4().hex[:8]
                self._candidates[best_id] = {"bbox": bbox, "first_seen": now_ts}
            else:
                self._candidates[best_id]["bbox"] = bbox
            seen_ids.add(best_id)

        for cid in [c for c in self._candidates if c not in seen_ids]:
            del self._candidates[cid]
            self._last_emitted.pop(cid, None)

        events = []
        for cid in seen_ids:
            candidate = self._candidates[cid]
            dwell = now_ts - candidate["first_seen"]
            if dwell < ABANDONED_SUSTAIN_SECONDS:
                continue
            last = self._last_emitted.get(cid)
            should_emit = last is None or (now_ts - last) >= COOLDOWN_SECONDS
            if should_emit:
                self._last_emitted[cid] = now_ts
            # Returned every tick once sustained (not just on the cooldown-gated
            # emission) so the live-feed overlay box stays visible the whole time,
            # not just for the one frame a new incident is raised.
            confidence = min(0.55, 0.25 + dwell / 200.0)  # capped low; longer dwell nudges it up slightly
            events.append({
                "bbox": candidate["bbox"],
                "warning_type": "abandoned_object",
                "dwell_seconds": dwell,
                "confidence": confidence,
                "emit": should_emit,
            })
        return events
