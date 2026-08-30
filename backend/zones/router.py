"""
backend/zones/router.py

Zone management — per-camera polygons.

GET    /cameras/{cam_id}/zones         — list zones for camera
POST   /cameras/{cam_id}/zones         — create zone (admin)
GET    /cameras/{cam_id}/zones/{id}    — get one zone
PATCH  /cameras/{cam_id}/zones/{id}    — update zone (admin)
DELETE /cameras/{cam_id}/zones/{id}    — delete zone (admin)

On create/update/delete the running DetectionPipeline is notified
to hot-reload its zone list without restart.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.auth.jwt import get_current_user, require_role
from backend.db.database import get_db
from backend.db.models import Camera, Zone
from backend.pipeline.pipeline_manager import PipelineManager, get_pipeline_manager
from backend.audit.chain import audit_log

logger = logging.getLogger(__name__)
router = APIRouter(tags=["zones"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ZoneCreate(BaseModel):
    name: str
    polygon_points: list[list[int]]   # [[x,y], [x,y], ...]
    zone_type: str                    # restricted | monitored | safe
    risk_level: int = 1

    @field_validator("polygon_points")
    @classmethod
    def min_three_points(cls, v):
        if len(v) < 3:
            raise ValueError("polygon_points must have at least 3 points")
        return v

    @field_validator("zone_type")
    @classmethod
    def valid_zone_type(cls, v):
        if v not in ("restricted", "monitored", "safe"):
            raise ValueError("zone_type must be restricted, monitored, or safe")
        return v

    @field_validator("risk_level")
    @classmethod
    def valid_risk(cls, v):
        if not (1 <= v <= 5):
            raise ValueError("risk_level must be between 1 and 5")
        return v


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    polygon_points: Optional[list[list[int]]] = None
    zone_type: Optional[str] = None
    risk_level: Optional[int] = None


class ZoneOut(BaseModel):
    id: int
    camera_id: int
    name: str
    polygon_points: list
    zone_type: str
    risk_level: int

    class Config:
        from_attributes = True


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/cameras/{camera_id}/zones", response_model=list[ZoneOut])
def list_zones(
    camera_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    _cam_or_404(db, camera_id)
    zones = db.query(Zone).filter(Zone.camera_id == camera_id).all()
    return [_zone_out(z) for z in zones]


@router.post("/cameras/{camera_id}/zones", response_model=ZoneOut, status_code=201)
def create_zone(
    camera_id: int,
    body: ZoneCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    _cam_or_404(db, camera_id)
    zone = Zone(
        camera_id=camera_id,
        name=body.name,
        polygon_points=json.dumps(body.polygon_points),
        zone_type=body.zone_type,
        risk_level=body.risk_level,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)

    _pipeline_reload_zones(pipeline_mgr, camera_id, db)
    audit_log(db, action="zone.create", actor_id=current_user.id,
              target_type="zone", target_id=zone.id,
              payload={"name": zone.name, "zone_type": zone.zone_type, "camera_id": camera_id})

    return _zone_out(zone)


@router.get("/cameras/{camera_id}/zones/{zone_id}", response_model=ZoneOut)
def get_zone(
    camera_id: int,
    zone_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_role("admin", "operator")),
):
    zone = _zone_or_404(db, camera_id, zone_id)
    return _zone_out(zone)


@router.patch("/cameras/{camera_id}/zones/{zone_id}", response_model=ZoneOut)
def update_zone(
    camera_id: int,
    zone_id: int,
    body: ZoneUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    zone = _zone_or_404(db, camera_id, zone_id)
    old = {"name": zone.name, "zone_type": zone.zone_type, "risk_level": zone.risk_level}

    if body.name is not None:
        zone.name = body.name
    if body.polygon_points is not None:
        if len(body.polygon_points) < 3:
            raise HTTPException(status_code=422, detail="polygon_points needs ≥ 3 points")
        zone.polygon_points = json.dumps(body.polygon_points)
    if body.zone_type is not None:
        if body.zone_type not in ("restricted", "monitored", "safe"):
            raise HTTPException(status_code=422, detail="Invalid zone_type")
        zone.zone_type = body.zone_type
    if body.risk_level is not None:
        if not (1 <= body.risk_level <= 5):
            raise HTTPException(status_code=422, detail="risk_level 1–5")
        zone.risk_level = body.risk_level

    db.commit()
    db.refresh(zone)

    _pipeline_reload_zones(pipeline_mgr, camera_id, db)
    audit_log(db, action="zone.update", actor_id=current_user.id,
              target_type="zone", target_id=zone.id,
              payload={"old": old, "new": {"name": zone.name, "zone_type": zone.zone_type}})

    return _zone_out(zone)


@router.delete("/cameras/{camera_id}/zones/{zone_id}", status_code=204)
def delete_zone(
    camera_id: int,
    zone_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
    pipeline_mgr: PipelineManager = Depends(get_pipeline_manager),
):
    zone = _zone_or_404(db, camera_id, zone_id)
    db.delete(zone)
    db.commit()

    _pipeline_reload_zones(pipeline_mgr, camera_id, db)
    audit_log(db, action="zone.delete", actor_id=current_user.id,
              target_type="zone", target_id=zone_id,
              payload={"camera_id": camera_id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cam_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return cam


def _zone_or_404(db: Session, camera_id: int, zone_id: int) -> Zone:
    zone = db.query(Zone).filter(Zone.id == zone_id, Zone.camera_id == camera_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found on camera {camera_id}")
    return zone


def _zone_out(z: Zone) -> dict:
    return {
        "id": z.id,
        "camera_id": z.camera_id,
        "name": z.name,
        "polygon_points": json.loads(z.polygon_points),
        "zone_type": z.zone_type,
        "risk_level": z.risk_level,
    }


def _pipeline_reload_zones(pipeline_mgr: PipelineManager, camera_id: int, db: Session):
    """Tell the running pipeline to reload zones from DB without restart."""
    import numpy as np
    pipeline = pipeline_mgr.get(camera_id)
    if pipeline is None:
        return
    try:
        zones = db.query(Zone).filter(Zone.camera_id == camera_id).all()
        pipeline._zones = [
            (z.id, np.array(json.loads(z.polygon_points), dtype=np.int32), z.zone_type)
            for z in zones
        ]
        logger.info("Pipeline cam %d: hot-reloaded %d zones", camera_id, len(zones))
    except Exception as exc:
        logger.error("Zone hot-reload failed cam %d: %s", camera_id, exc)
