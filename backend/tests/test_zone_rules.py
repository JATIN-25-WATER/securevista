import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detection.zone_rules import ZoneDef, ZoneRuleEngine

ZONE = ZoneDef(
    id="zone-1",
    name="Test Zone",
    polygon=[[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]],
    restricted=False,
    loitering_threshold_s=10,
    after_hours_monitored=False,
)

INSIDE = [0.5, 0.5, 0.55, 0.55]  # bbox whose centroid is inside ZONE
OUTSIDE = [0.05, 0.05, 0.1, 0.1]  # bbox whose centroid is well outside ZONE


def _loitering_fired(events):
    return any(e["event_type"] == "loitering" for e in events)


def test_loitering_fires_for_continuous_presence():
    engine = ZoneRuleEngine()
    engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=0.0)
    events = engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=11.0)
    assert _loitering_fired(events)


def test_brief_boundary_exit_within_grace_period_does_not_reset_dwell():
    # A track whose centroid steps just outside the polygon for one tick
    # (natural sway at a zone edge, or ordinary detection jitter) and comes
    # right back must still accumulate dwell across the gap -- this is the
    # exact case that was previously reset to zero on every such tick.
    engine = ZoneRuleEngine()
    engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=0.0)
    engine.evaluate({1: {"bbox": OUTSIDE}}, [ZONE], now_ts=2.0)  # brief exit, well under the 3s grace period
    events = engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=11.0)  # back inside, past the original threshold
    assert _loitering_fired(events)


def test_exit_longer_than_grace_period_does_reset_dwell():
    # A track genuinely gone for longer than LOITER_GRACE_PERIOD_SECONDS (3s)
    # must still get a fresh dwell clock -- the grace period tolerates
    # momentary jitter, not someone leaving and coming back much later.
    engine = ZoneRuleEngine()
    engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=0.0)
    engine.evaluate({1: {"bbox": OUTSIDE}}, [ZONE], now_ts=8.0)
    events = engine.evaluate({1: {"bbox": INSIDE}}, [ZONE], now_ts=15.0)  # gone for 7s, well past the grace period
    assert not _loitering_fired(events)
