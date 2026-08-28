from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import chain
from app.auth.deps import any_authenticated, get_current_user_flexible, require_roles
from app.db import get_db
from app.evidence.capture import create_evidence_package
from app.evidence.sign import public_key_pem, sha256_file, verify_digest
from app.models import EvidencePackage, Incident
from app.schemas.evidence import EvidencePackageOut, VerifyResult

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

require_capture = require_roles("admin", "operator", "supervisor")


@router.post("/{incident_id}/capture", response_model=EvidencePackageOut)
def capture_evidence(incident_id: str, db: Session = Depends(get_db), user=Depends(require_capture)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(404, "Incident not found")
    try:
        package = create_evidence_package(db, incident)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    chain.append(db, actor=user.username, action="evidence_captured", details={"incident_id": incident_id, "evidence_id": package.id})
    return package


@router.get("/incident/{incident_id}", response_model=list[EvidencePackageOut])
def list_evidence_for_incident(incident_id: str, db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return db.query(EvidencePackage).filter(EvidencePackage.incident_id == incident_id).order_by(EvidencePackage.created_at.desc()).all()


@router.get("/{evidence_id}/preview")
def get_preview(evidence_id: str, db: Session = Depends(get_db), user=Depends(get_current_user_flexible)):
    pkg = db.query(EvidencePackage).filter(EvidencePackage.id == evidence_id).first()
    if not pkg:
        raise HTTPException(404, "Evidence not found")
    return FileResponse(pkg.redacted_preview_path, media_type="video/mp4")


@router.get("/{evidence_id}/original")
def get_original(evidence_id: str, db: Session = Depends(get_db), user=Depends(get_current_user_flexible)):
    if user.role not in ("admin", "supervisor"):
        raise HTTPException(403, "Only admin/supervisor roles may access original (unredacted) evidence")
    pkg = db.query(EvidencePackage).filter(EvidencePackage.id == evidence_id).first()
    if not pkg:
        raise HTTPException(404, "Evidence not found")
    chain.append(db, actor=user.username, action="evidence_original_accessed", details={"evidence_id": evidence_id})
    return FileResponse(pkg.clip_path, media_type="video/mp4")


@router.get("/{evidence_id}/verify", response_model=VerifyResult)
def verify_evidence(evidence_id: str, db: Session = Depends(get_db), user=Depends(any_authenticated)):
    pkg = db.query(EvidencePackage).filter(EvidencePackage.id == evidence_id).first()
    if not pkg:
        raise HTTPException(404, "Evidence not found")
    computed = sha256_file(pkg.clip_path)
    sha_matches = computed == pkg.sha256
    sig_valid = verify_digest(pkg.sha256, pkg.signature)
    chain.append(db, actor=user.username, action="evidence_verified", details={"evidence_id": evidence_id, "sha256_matches": sha_matches, "signature_valid": sig_valid})
    return VerifyResult(
        evidence_id=evidence_id,
        sha256_matches=sha_matches,
        signature_valid=sig_valid,
        computed_sha256=computed,
        stored_sha256=pkg.sha256,
    )


@router.get("/public-key")
def get_public_key(user=Depends(any_authenticated)):
    return {"public_key_pem": public_key_pem()}
