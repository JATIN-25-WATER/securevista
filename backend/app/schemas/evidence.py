from datetime import datetime

from pydantic import BaseModel


class EvidencePackageOut(BaseModel):
    id: str
    incident_id: str
    redacted_preview_path: str
    sha256: str
    created_at: datetime

    class Config:
        from_attributes = True


class VerifyResult(BaseModel):
    evidence_id: str
    sha256_matches: bool
    signature_valid: bool
    computed_sha256: str
    stored_sha256: str
