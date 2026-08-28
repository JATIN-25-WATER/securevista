from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    ts_iso: str
    actor: str
    action: str
    details: dict
    prev_hash: str
    hash: str


class AuditVerifyOut(BaseModel):
    valid: bool
    total_entries: int
    broken_at_id: int | None
