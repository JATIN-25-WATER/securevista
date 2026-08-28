"""Deterministic scenario definitions + runner.

Each scenario is a fixed, hand-authored timeline of (track bbox, timestamp)
frames fed through the real zone-rule engine used in production. Because
every input (bboxes, timestamps, zone/schedule config) is explicit rather
than read from the system clock or a live video decode, running a scenario
twice always produces exactly the same sequence of events -- this is what
makes the replay deterministic and safe to assert on in CI.
"""
from dataclasses import dataclass, field

from app.detection.zone_rules import ZoneDef, ZoneRuleEngine


@dataclass
class ScenarioFrame:
    t: float  # seconds since scenario start
    tracks: dict[int, list[float]]  # track_id -> normalized [x1,y1,x2,y2]


@dataclass
class Scenario:
    id: str
    description: str
    zones: list[ZoneDef]
    frames: list[ScenarioFrame]
    expected_event_types: set[str]  # event types that MUST appear at least once


def _bbox_at(cx: float, cy: float, size: float = 0.08) -> list[float]:
    return [cx - size, cy - size, cx + size, cy + size]


RESTRICTED_ZONE = ZoneDef(
    id="zone-dock",
    name="Loading Dock - Restricted Area",
    polygon=[[0.15, 0.2], [0.85, 0.2], [0.85, 0.9], [0.15, 0.9]],
    restricted=True,
    loitering_threshold_s=20,
    after_hours_monitored=True,
    is_after_hours=False,
)

AFTER_HOURS_ZONE = ZoneDef(
    id="zone-lobby",
    name="Lobby",
    polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    restricted=False,
    loitering_threshold_s=30,
    after_hours_monitored=True,
    is_after_hours=True,
)

SCENARIOS: list[Scenario] = [
    Scenario(
        id="restricted_zone_breach",
        description="A person walks from outside the loading dock zone into it and stays.",
        zones=[RESTRICTED_ZONE],
        frames=[
            ScenarioFrame(t=0.0, tracks={1: _bbox_at(0.05, 0.5)}),   # outside the zone
            ScenarioFrame(t=1.0, tracks={1: _bbox_at(0.5, 0.5)}),    # now inside -> restricted_entry
            ScenarioFrame(t=2.0, tracks={1: _bbox_at(0.5, 0.5)}),
        ],
        expected_event_types={"restricted_entry"},
    ),
    Scenario(
        id="after_hours_loiter",
        description="A person is present in an after-hours zone long enough to also trigger loitering.",
        zones=[AFTER_HOURS_ZONE],
        frames=[
            ScenarioFrame(t=0.0, tracks={2: _bbox_at(0.5, 0.5)}),
            ScenarioFrame(t=5.0, tracks={2: _bbox_at(0.5, 0.5)}),
            ScenarioFrame(t=31.0, tracks={2: _bbox_at(0.5, 0.5)}),  # past the 30s loitering threshold
        ],
        expected_event_types={"after_hours", "loitering"},
    ),
    Scenario(
        id="transient_pass_through",
        description="A person crosses the frame without entering any zone -- must not raise any event.",
        zones=[RESTRICTED_ZONE],
        frames=[
            ScenarioFrame(t=0.0, tracks={3: _bbox_at(0.02, 0.02)}),
            ScenarioFrame(t=1.0, tracks={3: _bbox_at(0.05, 0.05)}),
        ],
        expected_event_types=set(),
    ),
]


def run_scenario(scenario: Scenario) -> list[dict]:
    engine = ZoneRuleEngine()
    all_events: list[dict] = []
    for frame in scenario.frames:
        tracks = {tid: {"bbox": bbox} for tid, bbox in frame.tracks.items()}
        events = engine.evaluate(tracks, scenario.zones, frame.t)
        all_events.extend(events)
    return all_events
