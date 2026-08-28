from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.access_sim.simulator import emit_access_event
from app.auth.deps import any_authenticated, require_admin_or_operator
from app.db import get_db
from app.models import AccessEvent

router = APIRouter(prefix="/api/access-events", tags=["access"])


@router.get("")
def list_access_events(limit: int = 50, db: Session = Depends(get_db), user=Depends(any_authenticated)):
    rows = db.query(AccessEvent).order_by(AccessEvent.ts.desc()).limit(limit).all()
    return [{"id": r.id, "ts": r.ts, "badge_token": r.badge_token, "zone_id": r.zone_id, "simulated": r.simulated} for r in rows]


@router.post("/simulate")
def simulate_access_event(zone_id: str | None = None, user=Depends(require_admin_or_operator)):
    try:
        event = emit_access_event(zone_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"id": event.id, "ts": event.ts, "badge_token": event.badge_token, "zone_id": event.zone_id}
