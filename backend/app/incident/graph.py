"""Incident Graph: correlates raw observations / camera-health transitions
into deduplicated Incident nodes, scores them, and attaches a deterministic
explanation. This is the only place Incident rows are created or re-scored."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.access_sim.simulator import has_recent_matching_access_event
from app.audit import chain
from app.detection.abandoned_object import ABANDONED_SUSTAIN_SECONDS
from app.detection.fall_heuristic import FALL_SUSTAIN_SECONDS
from app.detection.fire_smoke_heuristic import SUSTAIN_SECONDS as FIRE_SMOKE_SUSTAIN_SECONDS
from app.incident.explain import build_explanation
from app.incident.scoring import compute_confidence_score, compute_impact_score
from app.ingestion.event_bus import event_bus
from app.models import (
    Camera,
    Incident,
    IncidentEvent,
    IncidentObservation,
    IncidentSceneWarning,
    Observation,
    SceneWarning,
    Zone,
)

logger = logging.getLogger("cctv.incident_graph")

# Observation-sourced incident types: a tracked person triggered a zone rule
# or the fall heuristic. All three zone rules (restricted_entry/after_hours/
# loitering) plus fall_warning share the same Observation-backed ingest path.
OBSERVATION_INCIDENT_TYPES = {"restricted_entry", "after_hours", "loitering", "fall_warning"}
CAMERA_HEALTH_INCIDENT_TYPES = {
    "offline": "camera_offline",
    "frozen": "camera_frozen",
    "blackout": "camera_blackout",
    "blurred": "camera_blur",
}
SCENE_WARNING_INCIDENT_TYPES = {
    "abandoned_object": "abandoned_object_warning",
    "fire_smoke": "fire_smoke_warning",
}
DWELL_THRESHOLD_BY_INCIDENT_TYPE = {
    "fall_warning": FALL_SUSTAIN_SECONDS,
    "abandoned_object_warning": ABANDONED_SUSTAIN_SECONDS,
    "fire_smoke_warning": FIRE_SMOKE_SUSTAIN_SECONDS,
}


def _get_or_create_incident(db: Session, incident_type: str, dedup_key: str, camera_id: str, zone_id: str | None) -> tuple[Incident, bool]:
    existing = (
        db.query(Incident)
        .filter(Incident.dedup_key == dedup_key, Incident.status != "resolved")
        .order_by(Incident.opened_at.desc())
        .first()
    )
    if existing:
        return existing, False

    incident = Incident(
        type=incident_type,
        status="new",
        dedup_key=dedup_key,
        impact_score=0.0,
        confidence_score=0.0,
        explanation_json="{}",
        camera_id=camera_id,
        zone_id=zone_id,
    )
    db.add(incident)
    db.flush()
    db.add(IncidentEvent(incident_id=incident.id, actor_id=None, action="created", note=None))
    return incident, True


def ingest_observation(db: Session, obs: Observation):
    if obs.event_type not in OBSERVATION_INCIDENT_TYPES:
        return  # "presence" is informational only, not incident-worthy

    dedup_key = f"{obs.event_type}:{obs.camera_id}:{obs.zone_id}"
    incident, created = _get_or_create_incident(db, obs.event_type, dedup_key, obs.camera_id, obs.zone_id)

    already_linked = (
        db.query(IncidentObservation)
        .filter(IncidentObservation.incident_id == incident.id, IncidentObservation.observation_id == obs.id)
        .first()
    )
    if not already_linked:
        db.add(IncidentObservation(incident_id=incident.id, observation_id=obs.id))
        db.flush()

    _rescore(db, incident)
    db.commit()
    db.refresh(incident)

    if created:
        chain.append(db, actor="system", action="incident_created", details={"incident_id": incident.id, "type": incident.type})

    event_bus.publish({"type": "incident", "incident_id": incident.id, "status": incident.status, "created": created})


def _rescore(db: Session, incident: Incident):
    linked_obs = (
        db.query(Observation)
        .join(IncidentObservation, IncidentObservation.observation_id == Observation.id)
        .filter(IncidentObservation.incident_id == incident.id)
        .order_by(Observation.ts.asc())
        .all()
    )
    if not linked_obs:
        return

    camera = db.query(Camera).filter(Camera.id == incident.camera_id).first()
    zone = db.query(Zone).filter(Zone.id == incident.zone_id).first() if incident.zone_id else None

    observation_count = len(linked_obs)
    avg_conf = sum(o.confidence for o in linked_obs) / observation_count
    first_ts, last_ts = linked_obs[0].ts, linked_obs[-1].ts
    camera_status = camera.status if camera else "online"

    access_matched = has_recent_matching_access_event(db, incident.zone_id, last_ts)

    threshold_seconds = zone.loitering_threshold_s if (incident.type == "loitering" and zone) else DWELL_THRESHOLD_BY_INCIDENT_TYPE.get(incident.type)

    incident.impact_score = compute_impact_score(incident.type, observation_count, access_matched)
    incident.confidence_score = compute_confidence_score(incident.type, avg_conf, observation_count, camera_status)
    incident.explanation_json = json.dumps(build_explanation(
        incident_type=incident.type,
        camera_name=camera.name if camera else "unknown camera",
        zone_name=zone.name if zone else None,
        observation_count=observation_count,
        first_ts=first_ts.isoformat(),
        last_ts=last_ts.isoformat(),
        avg_confidence=avg_conf,
        camera_status_at_scoring=camera_status,
        access_event_matched=access_matched,
        threshold_seconds=threshold_seconds,
    ))


def ingest_scene_warning(db: Session, warning: SceneWarning):
    incident_type = SCENE_WARNING_INCIDENT_TYPES.get(warning.warning_type)
    if not incident_type:
        return

    dedup_key = f"{incident_type}:{warning.camera_id}:{warning.zone_id}"
    incident, created = _get_or_create_incident(db, incident_type, dedup_key, warning.camera_id, warning.zone_id)

    already_linked = (
        db.query(IncidentSceneWarning)
        .filter(IncidentSceneWarning.incident_id == incident.id, IncidentSceneWarning.scene_warning_id == warning.id)
        .first()
    )
    if not already_linked:
        db.add(IncidentSceneWarning(incident_id=incident.id, scene_warning_id=warning.id))
        db.flush()

    _rescore_scene(db, incident)
    db.commit()
    db.refresh(incident)

    if created:
        chain.append(db, actor="system", action="incident_created", details={"incident_id": incident.id, "type": incident.type})

    event_bus.publish({"type": "incident", "incident_id": incident.id, "status": incident.status, "created": created})


def _rescore_scene(db: Session, incident: Incident):
    linked = (
        db.query(SceneWarning)
        .join(IncidentSceneWarning, IncidentSceneWarning.scene_warning_id == SceneWarning.id)
        .filter(IncidentSceneWarning.incident_id == incident.id)
        .order_by(SceneWarning.ts.asc())
        .all()
    )
    if not linked:
        return

    camera = db.query(Camera).filter(Camera.id == incident.camera_id).first()
    zone = db.query(Zone).filter(Zone.id == incident.zone_id).first() if incident.zone_id else None

    observation_count = len(linked)
    avg_conf = sum(w.confidence for w in linked) / observation_count
    first_ts, last_ts = linked[0].ts, linked[-1].ts
    camera_status = camera.status if camera else "online"

    incident.impact_score = compute_impact_score(incident.type, observation_count, False)
    incident.confidence_score = compute_confidence_score(incident.type, avg_conf, observation_count, camera_status)
    incident.explanation_json = json.dumps(build_explanation(
        incident_type=incident.type,
        camera_name=camera.name if camera else "unknown camera",
        zone_name=zone.name if zone else None,
        observation_count=observation_count,
        first_ts=first_ts.isoformat(),
        last_ts=last_ts.isoformat(),
        avg_confidence=avg_conf,
        camera_status_at_scoring=camera_status,
        access_event_matched=False,
        threshold_seconds=DWELL_THRESHOLD_BY_INCIDENT_TYPE.get(incident.type),
    ))


def ingest_camera_health(db: Session, camera: Camera, prev_status: str):
    incident_type = CAMERA_HEALTH_INCIDENT_TYPES.get(camera.status)
    if incident_type:
        dedup_key = f"{incident_type}:{camera.id}"
        incident, created = _get_or_create_incident(db, incident_type, dedup_key, camera.id, None)
        incident.impact_score = compute_impact_score(incident_type, 1, False)
        incident.confidence_score = 90.0  # camera-health signals are directly measured, not detector-dependent
        incident.explanation_json = json.dumps(build_explanation(
            incident_type=incident_type,
            camera_name=camera.name,
            zone_name=None,
            observation_count=1,
            first_ts=datetime.now(timezone.utc).isoformat(),
            last_ts=datetime.now(timezone.utc).isoformat(),
            avg_confidence=1.0,
            camera_status_at_scoring=camera.status,
            access_event_matched=False,
        ))
        db.commit()
        db.refresh(incident)
        if created:
            chain.append(db, actor="system", action="incident_created", details={"incident_id": incident.id, "type": incident_type})
        event_bus.publish({"type": "incident", "incident_id": incident.id, "status": incident.status, "created": created})
        return

    if camera.status == "online":
        resolve_camera_health_incidents(db, camera)


def resolve_camera_health_incidents(db: Session, camera: Camera):
    open_incidents = (
        db.query(Incident)
        .filter(Incident.camera_id == camera.id, Incident.status != "resolved")
        .filter(Incident.type.in_(CAMERA_HEALTH_INCIDENT_TYPES.values()))
        .all()
    )
    for incident in open_incidents:
        incident.status = "resolved"
        incident.closed_at = datetime.now(timezone.utc)
        db.add(IncidentEvent(incident_id=incident.id, actor_id=None, action="resolved", note="Auto-resolved: camera health recovered to online."))
        db.commit()
        chain.append(db, actor="system", action="incident_auto_resolved", details={"incident_id": incident.id, "type": incident.type})
        event_bus.publish({"type": "incident", "incident_id": incident.id, "status": "resolved", "created": False})
