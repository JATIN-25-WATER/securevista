"""Simulated authorization/access-control event source.

Real access-control integration is explicitly out of scope for this
system. This module only ever produces clearly-labeled simulated events
(AccessEvent.simulated is always True) with opaque badge tokens -- no
real identity is modeled or stored.
"""
import logging
import random
import threading
import time

from app.db import SessionLocal
from app.models import AccessEvent, Zone

logger = logging.getLogger("cctv.access_sim")

MIN_INTERVAL_S = 45
MAX_INTERVAL_S = 90
CORRELATION_WINDOW_S = 60


def _random_badge_token() -> str:
    return f"BADGE-{random.randint(1000, 9999)}"


def emit_access_event(zone_id: str | None = None) -> AccessEvent:
    db = SessionLocal()
    try:
        if zone_id is None:
            zones = db.query(Zone).all()
            if not zones:
                zone_id = None
            else:
                zone_id = random.choice(zones).id
        elif db.query(Zone).filter(Zone.id == zone_id).first() is None:
            raise ValueError(f"Zone '{zone_id}' does not exist")
        event = AccessEvent(badge_token=_random_badge_token(), zone_id=zone_id, simulated=True)
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
    finally:
        db.close()


def has_recent_matching_access_event(db, zone_id: str | None, around_ts, window_s: float = CORRELATION_WINDOW_S) -> bool:
    if not zone_id or around_ts is None:
        return False
    from datetime import timedelta

    lo = around_ts - timedelta(seconds=window_s)
    hi = around_ts + timedelta(seconds=window_s)
    return (
        db.query(AccessEvent)
        .filter(AccessEvent.zone_id == zone_id, AccessEvent.ts >= lo, AccessEvent.ts <= hi)
        .first()
        is not None
    )


class AccessEventGenerator(threading.Thread):
    """Background thread producing believable, low-frequency simulated
    access events so the correlation feature has realistic traffic."""

    def __init__(self):
        super().__init__(daemon=True, name="access-event-generator")
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            wait_s = random.uniform(MIN_INTERVAL_S, MAX_INTERVAL_S)
            if self._stop_event.wait(wait_s):
                break
            try:
                event = emit_access_event()
                logger.info("Simulated access event: %s zone=%s", event.badge_token, event.zone_id)
            except Exception:
                logger.exception("Failed to emit simulated access event")


generator = AccessEventGenerator()
