"""
backend/audit/router.py

GET /audit          — paginated audit log (admin only)
GET /audit/verify   — verify chain integrity (admin only)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.jwt import require_role
from backend.db.database import get_db
from backend.db.models import AuditLog
from backend.audit.chain import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    entries = q.order_by(AuditLog.id.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": e.id,
            "action": e.action,
            "actor_id": e.actor_id,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "timestamp": e.timestamp.isoformat(),
            "payload": e.payload,
            "entry_hash": e.entry_hash,
        }
        for e in entries
    ]


@router.get("/verify")
def verify_audit_chain(
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin")),
):
    intact, bad_id = verify_chain(db)
    return {"intact": intact, "first_tampered_id": bad_id}
