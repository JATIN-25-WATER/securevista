import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import chain
from app.auth.deps import any_authenticated
from app.db import get_db
from app.models import AuditLog
from app.schemas.audit import AuditLogOut, AuditVerifyOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(limit: int = 200, db: Session = Depends(get_db), user=Depends(any_authenticated)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [
        AuditLogOut(
            id=r.id,
            ts_iso=r.ts_iso,
            actor=r.actor,
            action=r.action,
            details=json.loads(r.details_json),
            prev_hash=r.prev_hash,
            hash=r.hash,
        )
        for r in reversed(rows)
    ]


@router.get("/verify", response_model=AuditVerifyOut)
def verify_audit_log(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return chain.verify_chain(db)
