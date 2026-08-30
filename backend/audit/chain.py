"""
backend/audit/chain.py

Tamper-evident audit log.

Every entry is:
  entry_hash = sha256(prev_hash + timestamp + action + actor_id + payload_json)

The genesis row uses prev_hash = "0".
Verifying the chain means replaying every hash in insertion order.

Usage:
  from backend.audit.chain import audit_log

  audit_log(db, actor_id=1, action="incident.acknowledge",
            target_type="incident", target_id=5,
            payload={"old_status": "new", "new_status": "acknowledged"})
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.db.models import AuditLog

logger = logging.getLogger(__name__)


def _compute_hash(prev_hash: str, timestamp: datetime, action: str,
                  actor_id: Optional[int], payload: str) -> str:
    raw = f"{prev_hash}|{timestamp.isoformat()}|{action}|{actor_id}|{payload}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_prev_hash(db: Session) -> str:
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return last.entry_hash if last else "0"


def audit_log(
    db: Session,
    action: str,
    actor_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> AuditLog:
    """
    Append one entry to the audit chain.
    Commits the entry immediately (audit writes are always committed,
    even if the surrounding transaction rolls back).
    """
    ts = datetime.utcnow()
    prev_hash = _get_prev_hash(db)
    payload_json = json.dumps(payload or {}, sort_keys=True)
    entry_hash = _compute_hash(prev_hash, ts, action, actor_id, payload_json)

    entry = AuditLog(
        entry_hash=entry_hash,
        prev_hash=prev_hash,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        timestamp=ts,
        payload=payload_json,
    )
    db.add(entry)
    try:
        db.commit()
        db.refresh(entry)
    except Exception as exc:
        logger.error("Audit log write failed: %s", exc)
        db.rollback()
    return entry


def verify_chain(db: Session) -> tuple[bool, Optional[int]]:
    """
    Replay the entire audit chain and verify every hash.
    Returns (True, None) if intact, (False, first_bad_id) if tampered.
    """
    entries = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    prev_hash = "0"

    for entry in entries:
        expected = _compute_hash(
            prev_hash, entry.timestamp, entry.action, entry.actor_id, entry.payload or "{}"
        )
        if expected != entry.entry_hash:
            logger.error("Audit chain broken at entry id=%d", entry.id)
            return False, entry.id
        prev_hash = entry.entry_hash

    return True, None
