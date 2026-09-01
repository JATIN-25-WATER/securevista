"""
backend/cameras/router.py

Camera management endpoints.

CRUD:
  GET    /cameras          — list all cameras (admin, operator)
  POST   /cameras          — add camera (admin)
  GET    /cameras/{id}     — get one camera (admin, operator)
  PATCH  /cameras/{id}     — update name/uri (admin)
  DELETE /cameras/{id}     — remove camera (admin)

Pipeline control:
  POST   /cameras/{id}/start   — start detection pipeline (admin, operator)
  POST   /cameras/{id}/stop    — stop detection pipeline  (admin, operator)
  GET    /cameras/{id}/status  — live source status       (admin, operator)
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.jwt import get_current_user, require_role
from backend.db.database import get_db
from backend.db.models import Camera, Observation
from backend.pipeline.source_manager import SourceManager, get_source_manager
from backend.pipeline.pipeline_manager import PipelineManager, get_pipeline_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cameras", tags=["cameras"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    name: str
    source_uri: str   # file path, "0" for webcam, or rtsp://...


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    source_uri: Optional[str] = None


class CameraOut(BaseModel):
    id: int
    name: str
    source_uri: str
    status: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CameraOut])
def list_cameras(
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
):
    cameras = db.query(Camera).all()
    if user.username == "operator 1":
        return [c for c in cameras if c.id == 1]
    elif user.username == "operator 2":
        return [c for c in cameras if c.id == 2]
    elif user.username == "operator 3":
        return [c for c in cameras if c.id == 3]
    return cameras


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(
    body: CameraCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin")),
    source_mgr: SourceManager = Depends(get_source_manager),
):
    cam = Camera(name=body.name, source_uri=body.source_uri, status="unknown")
    db.add(cam)
    db.commit()
    db.refresh(cam)
    # Register in source manager (not started yet)
    source_mgr.add(camera_id=cam.id, source_uri=cam.source_uri)
    logger.info("Camera created: id=%d name=%s", cam.id, cam.name)
    return cam


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
):
    _check_operator_camera_access(user, camera_id)
    cam = _get_or_404(db, camera_id)
    return cam


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: int,
    body: CameraUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    cam = _get_or_404(db, camera_id)

    uri_changed = body.source_uri and body.source_uri != cam.source_uri

    if body.name:
        cam.name = body.name
    if body.source_uri:
        cam.source_uri = body.source_uri

    db.commit()
    db.refresh(cam)

    if uri_changed:
        # Stop pipeline + source, re-register with new URI
        pipeline_mgr.detach(camera_id)
        source_mgr.remove(camera_id)
        source_mgr.add(camera_id=camera_id, source_uri=cam.source_uri)
        _sync_status(db, cam, "unknown")

    return cam


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    cam = _get_or_404(db, camera_id)
    pipeline_mgr.detach(camera_id)
    source_mgr.remove(camera_id)
    db.delete(cam)
    db.commit()


# ── Pipeline control ─────────────────────────────────────────────────────────

@router.post("/{camera_id}/start")
def start_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    _check_operator_camera_access(user, camera_id)
    cam = _get_or_404(db, camera_id)

    # Ensure source is registered
    src = source_mgr.get(camera_id)
    if src is None:
        src = source_mgr.add(camera_id=camera_id, source_uri=cam.source_uri)

    ok = source_mgr.start(camera_id)
    if not ok:
        _sync_status(db, cam, "offline")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to open source '{cam.source_uri}'",
        )

    pipeline_mgr.attach(source=src, camera_db_id=camera_id)
    _sync_status(db, cam, "active")
    return {"camera_id": camera_id, "status": "active"}


@router.post("/{camera_id}/stop")
def stop_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    _check_operator_camera_access(user, camera_id)
    cam = _get_or_404(db, camera_id)
    pipeline_mgr.detach(camera_id)
    source_mgr.stop(camera_id)
    _sync_status(db, cam, "offline")
    return {"camera_id": camera_id, "status": "offline"}


@router.get("/{camera_id}/status")
def camera_status(
    camera_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
    source_mgr: SourceManager = Depends(get_source_manager),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    _check_operator_camera_access(user, camera_id)
    _get_or_404(db, camera_id)
    src = source_mgr.get(camera_id)
    pipeline_running = pipeline_mgr.get(camera_id) is not None

    if src is None:
        return {"camera_id": camera_id, "state": "unregistered", "pipeline": False}

    status_data = src.status_dict()
    status_data["pipeline"] = pipeline_running
    return status_data


# ── Observations endpoint ─────────────────────────────────────────────────────

@router.get("/{camera_id}/observations")
def list_observations(
    camera_id: int,
    limit: int = 50,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "operator", "responder")),
):
    """Return recent observations for a camera, newest first."""
    _check_operator_camera_access(user, camera_id)
    _get_or_404(db, camera_id)
    q = db.query(Observation).filter(Observation.camera_id == camera_id)
    if event_type:
        q = q.filter(Observation.event_type == event_type)
    obs = q.order_by(Observation.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": o.id,
            "track_id": o.track_id,
            "event_type": o.event_type,
            "timestamp": o.timestamp.isoformat(),
            "zone_id": o.zone_id,
            "confidence_score": o.confidence_score,
            "impact_score": o.impact_score,
            "explanation": o.explanation,
        }
        for o in obs
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if cam is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return cam


def _sync_status(db: Session, cam: Camera, new_status: str):
    cam.status = new_status
    db.commit()


def _check_operator_camera_access(user, camera_id: int):
    if user and user.username == "operator 1" and camera_id != 1:
        raise HTTPException(status_code=403, detail="Operator 1 is restricted to Camera 1")
    if user and user.username == "operator 2" and camera_id != 2:
        raise HTTPException(status_code=403, detail="Operator 2 is restricted to Camera 2")
    if user and user.username == "operator 3" and camera_id != 3:
        raise HTTPException(status_code=403, detail="Operator 3 is restricted to Camera 3")
