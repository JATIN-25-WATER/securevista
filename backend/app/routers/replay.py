"""Policy replay & threshold simulation: preview how a proposed zone
threshold/flag change would have played out against a deterministic
scenario, without touching any live zone config. Pure computation over the
same ZoneRuleEngine used in production -- nothing here reads or writes the
live database."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_admin
from app.detection.zone_rules import ZoneDef, ZoneRuleEngine
from app.replay.scenarios import SCENARIOS, run_scenario

router = APIRouter(prefix="/api/replay", tags=["replay"])


class ZoneOverride(BaseModel):
    restricted: bool | None = None
    loitering_threshold_s: int | None = None
    after_hours_monitored: bool | None = None


class SimulateIn(BaseModel):
    scenario_id: str
    zone_overrides: dict[str, ZoneOverride] = {}  # zone id -> override


def _summarize(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1
    return counts


@router.get("/scenarios")
def list_scenarios(user=Depends(require_admin)):
    return [
        {
            "id": s.id,
            "description": s.description,
            "expected_event_types": sorted(s.expected_event_types),
            "zones": [{"id": z.id, "name": z.name, "restricted": z.restricted, "loitering_threshold_s": z.loitering_threshold_s, "after_hours_monitored": z.after_hours_monitored} for z in s.zones],
        }
        for s in SCENARIOS
    ]


@router.post("/simulate")
def simulate_policy(payload: SimulateIn, user=Depends(require_admin)):
    scenario = next((s for s in SCENARIOS if s.id == payload.scenario_id), None)
    if not scenario:
        raise HTTPException(404, "Unknown scenario")

    baseline_events = run_scenario(scenario)

    proposed_zones = []
    for zone in scenario.zones:
        override = payload.zone_overrides.get(zone.id)
        if override:
            proposed_zones.append(ZoneDef(
                id=zone.id,
                name=zone.name,
                polygon=zone.polygon,
                restricted=zone.restricted if override.restricted is None else override.restricted,
                loitering_threshold_s=zone.loitering_threshold_s if override.loitering_threshold_s is None else override.loitering_threshold_s,
                after_hours_monitored=zone.after_hours_monitored if override.after_hours_monitored is None else override.after_hours_monitored,
                is_after_hours=zone.is_after_hours,
            ))
        else:
            proposed_zones.append(zone)

    engine = ZoneRuleEngine()
    proposed_events: list[dict] = []
    for frame in scenario.frames:
        tracks = {tid: {"bbox": bbox} for tid, bbox in frame.tracks.items()}
        proposed_events.extend(engine.evaluate(tracks, proposed_zones, frame.t))

    return {
        "scenario_id": scenario.id,
        "description": scenario.description,
        "baseline": _summarize(baseline_events),
        "proposed": _summarize(proposed_events),
    }
