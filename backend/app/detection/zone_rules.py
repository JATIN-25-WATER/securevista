"""Restricted-zone entry, after-hours presence, and loitering rules.

Pure and deterministic: every method takes the current timestamp as an
explicit argument rather than reading the system clock, so the exact
same sequence of frames + timestamps always produces the exact same
events — required for deterministic scenario replay (requirement 27).
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

EVENT_COOLDOWN_SECONDS = 5.0

# A track's dwell clock is only reset if it's been out of the zone for longer
# than this. Without a grace period, a single tick where a person's bbox
# centroid lands just outside the polygon -- natural body sway at a zone
# boundary, a doorway edge, normal detection jitter -- silently resets their
# loitering clock to zero every time it happens, systematically
# under-counting dwell time for exactly the borderline-position cases an
# operator most needs loitering to catch. 3s matches the centroid tracker's
# own max_disappeared grace (15 ticks at the 5fps detection rate).
LOITER_GRACE_PERIOD_SECONDS = 3.0


@dataclass
class ZoneDef:
    id: str
    name: str
    polygon: list[list[float]]  # normalized [x,y] points
    restricted: bool
    loitering_threshold_s: int
    after_hours_monitored: bool
    is_after_hours: bool = False  # resolved by the caller from Schedule data before each evaluate() call

    def contains(self, x: float, y: float) -> bool:
        pts = np.array(self.polygon, dtype=np.float32).reshape((-1, 1, 2))
        return cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0


@dataclass
class ZoneRuleEngine:
    """One instance per camera."""

    zone_entry_time: dict = field(default_factory=dict)  # (track_id, zone_id) -> first-seen ts
    zone_last_seen: dict = field(default_factory=dict)  # (track_id, zone_id) -> ts last inside the zone
    last_emitted: dict = field(default_factory=dict)  # (track_id, zone_id, event_type) -> last-emit ts

    def evaluate(self, tracks: dict[int, dict], zones: list[ZoneDef], now_ts: float) -> list[dict]:
        events = []
        seen_this_tick = set()

        for track_id, info in tracks.items():
            x1, y1, x2, y2 = info["bbox"]
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

            in_any_zone = False
            for zone in zones:
                if not zone.contains(cx, cy):
                    continue
                in_any_zone = True
                key = (track_id, zone.id)
                seen_this_tick.add(key)
                if key not in self.zone_entry_time:
                    self.zone_entry_time[key] = now_ts
                self.zone_last_seen[key] = now_ts
                dwell = now_ts - self.zone_entry_time[key]

                fired_types = []
                if zone.restricted:
                    fired_types.append("restricted_entry")
                if zone.after_hours_monitored and zone.is_after_hours:
                    fired_types.append("after_hours")
                if dwell >= zone.loitering_threshold_s:
                    fired_types.append("loitering")
                if not fired_types:
                    fired_types.append("presence")

                for event_type in fired_types:
                    emit_key = (track_id, zone.id, event_type)
                    last = self.last_emitted.get(emit_key)
                    if last is not None and (now_ts - last) < EVENT_COOLDOWN_SECONDS:
                        continue
                    self.last_emitted[emit_key] = now_ts
                    events.append({
                        "track_id": track_id,
                        "zone_id": zone.id,
                        "event_type": event_type,
                        "bbox": info["bbox"],
                        "dwell_seconds": dwell,
                    })

            if not in_any_zone:
                # track is on-camera but outside any defined zone: no zone-scoped event.
                pass

        # Forget dwell timers for (track, zone) pairs absent longer than the
        # grace period -- NOT immediately on the first tick they're missing.
        # A pair still within the grace window is left alone entirely (both
        # zone_entry_time and zone_last_seen untouched), so if the track
        # reappears in the zone before the grace period elapses, dwell
        # continues counting through the gap as if it was never interrupted.
        stale = [
            k for k in self.zone_entry_time
            if k not in seen_this_tick and (now_ts - self.zone_last_seen.get(k, now_ts)) > LOITER_GRACE_PERIOD_SECONDS
        ]
        for k in stale:
            del self.zone_entry_time[k]
            self.zone_last_seen.pop(k, None)

        return events
