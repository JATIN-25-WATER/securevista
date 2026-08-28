"""Fall/collapse heuristic: a deterministic bounding-box aspect-ratio check,
NOT a validated fall-detection classifier. It is scored and worded as a
low-confidence warning that needs human verification -- see
incident/scoring.py's confidence cap and incident/explain.py's wording for
this type.

A standing/walking person's bbox is taller than wide (width/height < 1). A
person lying on the ground typically produces a bbox wider than tall. This
flags a track that (1) was recently upright, (2) is now flat, and (3) has
stayed flat for FALL_SUSTAIN_SECONDS -- so a single noisy frame or someone
briefly bending over does not fire it.

Pure and deterministic: evaluate() takes the current timestamp as an
explicit argument rather than reading the system clock, matching
detection/zone_rules.py's pattern so this is unit-testable without wall time.
"""
from dataclasses import dataclass, field

FALL_ASPECT_RATIO_THRESHOLD = 1.4  # width/height above this looks "lying down"
UPRIGHT_ASPECT_RATIO_THRESHOLD = 1.0  # width/height below this looks "standing"
FALL_SUSTAIN_SECONDS = 3.0
FALL_COOLDOWN_SECONDS = 30.0


@dataclass
class FallHeuristic:
    """One instance per camera."""

    was_upright: dict = field(default_factory=dict)  # track_id -> bool, last confident stance
    flat_since: dict = field(default_factory=dict)  # track_id -> ts first seen flat since being upright
    last_emitted: dict = field(default_factory=dict)  # track_id -> ts of last emitted warning

    def evaluate(self, tracks: dict[int, dict], now_ts: float) -> list[dict]:
        events = []
        seen = set()

        for track_id, info in tracks.items():
            seen.add(track_id)
            x1, y1, x2, y2 = info["bbox"]
            w, h = max(1e-6, x2 - x1), max(1e-6, y2 - y1)
            ratio = w / h

            if ratio <= UPRIGHT_ASPECT_RATIO_THRESHOLD:
                self.was_upright[track_id] = True
                self.flat_since.pop(track_id, None)
                continue

            if ratio >= FALL_ASPECT_RATIO_THRESHOLD and self.was_upright.get(track_id):
                if track_id not in self.flat_since:
                    self.flat_since[track_id] = now_ts
                dwell = now_ts - self.flat_since[track_id]
                if dwell >= FALL_SUSTAIN_SECONDS:
                    last = self.last_emitted.get(track_id)
                    should_emit = last is None or (now_ts - last) >= FALL_COOLDOWN_SECONDS
                    if should_emit:
                        self.last_emitted[track_id] = now_ts
                    # Always returned once sustained, every tick, so the live-feed
                    # overlay can keep showing the box for the whole warning window --
                    # `emit` alone gates whether a new Observation/incident is raised
                    # (cooldown-limited), so we don't spam duplicate incidents.
                    confidence = min(0.55, 0.25 + dwell / 60.0)  # deliberately capped low
                    events.append({
                        "track_id": track_id,
                        "bbox": info["bbox"],
                        "event_type": "fall_warning",
                        "dwell_seconds": dwell,
                        "confidence": confidence,
                        "emit": should_emit,
                    })
            # ratio between the two thresholds is ambiguous (e.g. crouching) -- no state change

        for track_id in [t for t in self.flat_since if t not in seen]:
            del self.flat_since[track_id]
        for track_id in [t for t in self.was_upright if t not in seen]:
            del self.was_upright[track_id]

        return events
