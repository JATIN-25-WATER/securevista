"""
backend/incidents/correlator.py

Auto-incident creation logic.

When a high-impact Observation arrives, we:
1. Compute a dedup_hash (camera + event_type + 5-minute bucket)
2. If an open incident with that hash exists → link observation to it
3. Else → create new Incident, link observation, write audit entry

This runs synchronously when called from the incidents router or
can be triggered from the detection pipeline.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Incident, IncidentObservation, Observation
from backend.audit.chain import audit_log

logger = logging.getLogger(__name__)

# Observations with impact >= this threshold auto-create incidents
AUTO_INCIDENT_THRESHOLD = 0.6

# Dedup window — same camera + event_type within this window = same incident
DEDUP_WINDOW_MINUTES = 5


def _bucket(ts: datetime) -> str:
    """5-minute time bucket string for dedup."""
    bucket_start = ts.replace(second=0, microsecond=0)
    bucket_start = bucket_start.replace(
        minute=(ts.minute // DEDUP_WINDOW_MINUTES) * DEDUP_WINDOW_MINUTES
    )
    return bucket_start.isoformat()


def _dedup_hash(camera_id: int, event_type: str, ts: datetime) -> str:
    raw = f"{camera_id}:{event_type}:{_bucket(ts)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def maybe_create_incident(
    db: Session,
    observation: Observation,
    actor_id: Optional[int] = None,
) -> Optional[Incident]:
    """
    Called after an Observation is written.
    Creates or updates an Incident if impact_score >= threshold.
    Returns the Incident (new or existing) or None if below threshold.
    """
    if observation.impact_score < AUTO_INCIDENT_THRESHOLD:
        return None

    dhash = _dedup_hash(observation.camera_id, observation.event_type, observation.timestamp)

    # Check for open incident with same dedup hash
    existing = (
        db.query(Incident)
        .filter(
            Incident.dedup_hash == dhash,
            Incident.status.in_(["new", "acknowledged", "investigating"]),
        )
        .first()
    )

    if existing:
        # Link observation to existing incident (if not already linked)
        already_linked = (
            db.query(IncidentObservation)
            .filter(
                IncidentObservation.incident_id == existing.id,
                IncidentObservation.observation_id == observation.id,
            )
            .first()
        )
        if not already_linked:
            link = IncidentObservation(
                incident_id=existing.id,
                observation_id=observation.id,
            )
            db.add(link)
            # Extend correlation window
            existing.correlation_window_end = observation.timestamp
            db.commit()
            logger.debug("Observation %d linked to existing incident %d", observation.id, existing.id)
        return existing

    # New incident
    window_start = observation.timestamp
    window_end = observation.timestamp + timedelta(minutes=DEDUP_WINDOW_MINUTES)

    incident = Incident(
        status="new",
        dedup_hash=dhash,
        correlation_window_start=window_start,
        correlation_window_end=window_end,
    )
    db.add(incident)
    db.flush()   # get incident.id

    link = IncidentObservation(
        incident_id=incident.id,
        observation_id=observation.id,
    )
    db.add(link)
    db.commit()

    audit_log(
        db,
        action="incident.auto_create",
        actor_id=actor_id,
        target_type="incident",
        target_id=incident.id,
        payload={
            "trigger_observation_id": observation.id,
            "event_type": observation.event_type,
            "camera_id": observation.camera_id,
            "impact_score": observation.impact_score,
        },
    )

    logger.info(
        "Auto-incident %d created (camera=%d event=%s impact=%.2f)",
        incident.id, observation.camera_id, observation.event_type, observation.impact_score,
    )
    return incident
