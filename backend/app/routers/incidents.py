import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import any_authenticated
from app.db import get_db
from app.incident.lifecycle import apply_action
from app.models import Incident
from app.schemas.incident import IncidentActionIn, IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _incident_out(inc: Incident) -> IncidentOut:
    return IncidentOut(
        id=inc.id,
        type=inc.type,
        status=inc.status,
        impact_score=inc.impact_score,
        confidence_score=inc.confidence_score,
        explanation=json.loads(inc.explanation_json or "{}"),
        camera_id=inc.camera_id,
        zone_id=inc.zone_id,
        opened_at=inc.opened_at,
        updated_at=inc.updated_at,
        closed_at=inc.closed_at,
        disposition=inc.disposition,
        events=inc.events,
    )


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user=Depends(any_authenticated),
):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    rows = q.order_by(Incident.opened_at.desc()).limit(limit).all()
    return [_incident_out(r) for r in rows]


@router.get("/analytics/false-positives")
def false_positive_analytics(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    """Surfaces which camera/incident-type generates the most noise, based on
    responder-set dispositions at resolve time. Never inferred automatically."""
    rows = db.query(Incident).filter(Incident.disposition.isnot(None)).all()

    def _bucket(rows, key_fn):
        buckets: dict[str, dict] = {}
        for inc in rows:
            key = key_fn(inc)
            b = buckets.setdefault(key, {"total": 0, "false_positive": 0})
            b["total"] += 1
            if inc.disposition == "false_positive":
                b["false_positive"] += 1
        for b in buckets.values():
            b["false_positive_rate"] = round(b["false_positive"] / b["total"], 3) if b["total"] else 0.0
        return buckets

    return {
        "total_dispositioned": len(rows),
        "by_type": _bucket(rows, lambda i: i.type),
        "by_camera_id": _bucket(rows, lambda i: i.camera_id or "unknown"),
    }


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db), user=Depends(any_authenticated)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident not found")
    return _incident_out(inc)


@router.post("/{incident_id}/action", response_model=IncidentOut)
def act_on_incident(
    incident_id: str,
    payload: IncidentActionIn,
    db: Session = Depends(get_db),
    user=Depends(any_authenticated),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident not found")
    inc = apply_action(db, inc, payload.action, user.id, user.username, payload.note, payload.disposition)
    return _incident_out(inc)
