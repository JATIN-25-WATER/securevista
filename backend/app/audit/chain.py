"""Hash-chained security audit trail.

Each row's hash covers its own content plus the previous row's hash
(hash = sha256(prev_hash + canonical_json(details))), so any edit or
deletion of a past row is detectable by re-walking the chain. This is a
local, verifiable hash chain — not a distributed ledger/blockchain.
"""
import hashlib
import json
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditLog

GENESIS_HASH = "0" * 64

# append() is read-last-row-then-insert, which is not atomic on its own: two
# threads (every router handler runs as a sync `def`, i.e. on FastAPI's
# threadpool) can both read the same "last" row before either commits,
# producing two rows with the same prev_hash and making verify_chain report
# a false break. A single process-wide lock fully serializes appends, which
# is sufficient because this app always runs as one process (see start.ps1 --
# no multi-worker uvicorn).
_append_lock = threading.Lock()


def _canonical(details: dict) -> str:
    return json.dumps(details, sort_keys=True, separators=(",", ":"), default=str)


def _row_hash(prev_hash: str, actor: str, action: str, ts_iso: str, details: dict) -> str:
    payload = f"{prev_hash}|{actor}|{action}|{ts_iso}|{_canonical(details)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append(db: Session, actor: str, action: str, details: dict | None = None) -> AuditLog:
    details = details or {}
    with _append_lock:
        last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev_hash = last.hash if last else GENESIS_HASH
        ts = datetime.now(timezone.utc)
        ts_iso = ts.isoformat()
        row_hash = _row_hash(prev_hash, actor, action, ts_iso, details)
        entry = AuditLog(
            ts_iso=ts_iso,
            actor=actor,
            action=action,
            details_json=_canonical(details),
            prev_hash=prev_hash,
            hash=row_hash,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry


def verify_chain(db: Session) -> dict:
    """Re-walks the entire audit log and confirms every row's hash is consistent
    with its stored content and the previous row's hash."""
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    prev_hash = GENESIS_HASH
    broken_at = None
    for row in rows:
        details = json.loads(row.details_json)
        expected = _row_hash(prev_hash, row.actor, row.action, row.ts_iso, details)
        if row.prev_hash != prev_hash or row.hash != expected:
            broken_at = row.id
            break
        prev_hash = row.hash
    return {
        "valid": broken_at is None,
        "total_entries": len(rows),
        "broken_at_id": broken_at,
    }
