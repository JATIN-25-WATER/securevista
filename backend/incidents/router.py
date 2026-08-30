"""
backend/incidents/router.py

Incident lifecycle endpoints.

GET    /incidents              — list incidents (all roles)
POST   /incidents              — manually create (admin, operator)
GET    /incidents/{id}         — get one incident with linked observations
PATCH  /incidents/{id}/status  — status transition (admin, operator, responder*)
POST   /incidents/{id}/assign  — assign to user (admin, operator)

Status machine:
  new → acknowledged → investigating → escalated → resolved
  Any open status → resolved (admin/operator only)
  responder can only: acknowledged → investigating, investigating → escalated

Audit trail: every mutation logged.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.jwt import get_current_user, require_role
from backend.db.database import get_db
from backend.db.models import Incident, IncidentObservation, Observation, User
from backend.audit.chain import audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])

VALID_STATUSES = ("new", "acknowledged", "investigating", "escalated", "resolved")

# What each role is allowed to transition to
ROLE_ALLOWED_TRANSITIONS = {
    "admin":    set(VALID_STATUSES),
    "operator": set(VALID_STATUSES),
    "responder": {"acknowledged", "investigating", "escalated"},
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class IncidentCreate(BaseModel):
    observation_ids: list[int]
    note: Optional[str] = None


class StatusUpdate(BaseModel):
    new_status: str
    note: Optional[str] = None


class AssignRequest(BaseModel):
    user_id: int


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    q = db.query(Incident)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status_filter}")
        q = q.filter(Incident.status == status_filter)
    incidents = q.order_by(Incident.created_at.desc()).offset(skip).limit(limit).all()
    return [_incident_summary(i) for i in incidents]


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{incident_id}")
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator", "responder")),
):
    incident = _get_or_404(db, incident_id)
    obs = _linked_observations(db, incident_id)
    return {**_incident_summary(incident), "observations": obs}


# ── Manual create ─────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_incident(
    body: IncidentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin", "operator")),
):
    # Validate all observation IDs exist
    obs_list = db.query(Observation).filter(Observation.id.in_(body.observation_ids)).all()
    found_ids = {o.id for o in obs_list}
    missing = set(body.observation_ids) - found_ids
    if missing:
        raise HTTPException(status_code=422, detail=f"Observation IDs not found: {missing}")

    incident = Incident(
        status="new",
        correlation_window_start=min(o.timestamp for o in obs_list),
        correlation_window_end=max(o.timestamp for o in obs_list),
    )
    db.add(incident)
    db.flush()

    for obs in obs_list:
        db.add(IncidentObservation(incident_id=incident.id, observation_id=obs.id))
    db.commit()

    audit_log(
        db,
        action="incident.manual_create",
        actor_id=current_user.id,
        target_type="incident",
        target_id=incident.id,
        payload={"observation_ids": body.observation_ids, "note": body.note},
    )

    return _incident_summary(incident)


# ── Status transition ─────────────────────────────────────────────────────────

@router.patch("/{incident_id}/status")
def update_status(
    incident_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin", "operator", "responder")),
):
    incident = _get_or_404(db, incident_id)

    if body.new_status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.new_status}")

    allowed = ROLE_ALLOWED_TRANSITIONS.get(current_user.role, set())
    if body.new_status not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role}' cannot set status '{body.new_status}'",
        )

    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Resolved incidents cannot be re-opened")

    old_status = incident.status
    incident.status = body.new_status
    incident.updated_at = datetime.utcnow()
    db.commit()

    audit_log(
        db,
        action=f"incident.{body.new_status}",
        actor_id=current_user.id,
        target_type="incident",
        target_id=incident_id,
        payload={"old_status": old_status, "new_status": body.new_status, "note": body.note},
    )

    return _incident_summary(incident)


# ── Assign ────────────────────────────────────────────────────────────────────

@router.post("/{incident_id}/assign")
def assign_incident(
    incident_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin", "operator")),
):
    incident = _get_or_404(db, incident_id)

    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")

    old_assignee = incident.assigned_to
    incident.assigned_to = body.user_id
    incident.updated_at = datetime.utcnow()
    db.commit()

    audit_log(
        db,
        action="incident.assign",
        actor_id=current_user.id,
        target_type="incident",
        target_id=incident_id,
        payload={"old_assignee": old_assignee, "new_assignee": body.user_id},
    )

    return {"incident_id": incident_id, "assigned_to": body.user_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, incident_id: int) -> Incident:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return inc


def _incident_summary(i: Incident) -> dict:
    return {
        "id": i.id,
        "status": i.status,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
        "assigned_to": i.assigned_to,
        "dedup_hash": i.dedup_hash,
        "correlation_window_start": i.correlation_window_start.isoformat() if i.correlation_window_start else None,
        "correlation_window_end": i.correlation_window_end.isoformat() if i.correlation_window_end else None,
        "observation_count": len(i.observation_links),
        "evidence_count": len(i.evidence_packages),
    }


def _linked_observations(db: Session, incident_id: int) -> list[dict]:
    links = (
        db.query(IncidentObservation)
        .filter(IncidentObservation.incident_id == incident_id)
        .all()
    )
    obs_ids = [l.observation_id for l in links]
    observations = db.query(Observation).filter(Observation.id.in_(obs_ids)).all()
    return [
        {
            "id": o.id,
            "camera_id": o.camera_id,
            "event_type": o.event_type,
            "timestamp": o.timestamp.isoformat(),
            "confidence_score": o.confidence_score,
            "impact_score": o.impact_score,
            "explanation": o.explanation,
        }
        for o in observations
    ]
