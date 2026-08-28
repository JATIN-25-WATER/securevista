from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit import chain
from app.models import Incident, IncidentEvent

ACTION_TO_STATUS = {
    "acknowledge": "acknowledged",
    "investigate": "investigating",
    "escalate": "escalated",
    "resolve": "resolved",
}

ALLOWED_ACTIONS_FROM = {
    "new": {"acknowledge", "investigate", "resolve"},
    "acknowledged": {"investigate", "escalate", "resolve"},
    "investigating": {"escalate", "resolve"},
    "escalated": {"resolve"},
    "resolved": set(),
}

DISPOSITIONS = {"true_positive", "false_positive", "uncertain"}


def apply_action(
    db: Session,
    incident: Incident,
    action: str,
    actor_id: str,
    actor_username: str,
    note: str | None,
    disposition: str | None = None,
) -> Incident:
    allowed = ALLOWED_ACTIONS_FROM.get(incident.status, set())
    if action not in allowed:
        raise HTTPException(400, f"Cannot '{action}' an incident in status '{incident.status}'")
    if disposition is not None and disposition not in DISPOSITIONS:
        raise HTTPException(400, f"disposition must be one of {sorted(DISPOSITIONS)}")

    new_status = ACTION_TO_STATUS[action]
    incident.status = new_status
    if new_status == "resolved":
        incident.closed_at = datetime.now(timezone.utc)
        if disposition is not None:
            incident.disposition = disposition

    db.add(IncidentEvent(incident_id=incident.id, actor_id=actor_id, action=action, note=note))
    db.commit()
    db.refresh(incident)

    chain.append(db, actor=actor_username, action=f"incident_{action}", details={"incident_id": incident.id, "new_status": new_status, "disposition": disposition})
    return incident
