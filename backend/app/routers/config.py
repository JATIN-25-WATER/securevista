import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import chain
from app.auth.deps import any_authenticated, require_admin
from app.db import get_db
from app.incident.graph import resolve_camera_health_incidents
from app.ingestion.source_manager import source_manager
from app.models import AccessEvent, Camera, CameraStatus, Incident, Observation, SOP, Schedule, Zone
from app.schemas.config import (
    CameraIn,
    CameraOut,
    SOPIn,
    SOPOut,
    ScheduleIn,
    ScheduleOut,
    ZoneIn,
    ZoneOut,
)

router = APIRouter(prefix="/api/config", tags=["config"])


def _zone_out(z: Zone) -> ZoneOut:
    return ZoneOut(
        id=z.id,
        camera_id=z.camera_id,
        name=z.name,
        polygon=json.loads(z.polygon_json),
        restricted=z.restricted,
        loitering_threshold_s=z.loitering_threshold_s,
        after_hours_monitored=z.after_hours_monitored,
    )


def _schedule_out(s: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        scope=s.scope,
        scope_id=s.scope_id,
        business_hours=json.loads(s.business_hours_json),
    )


# ---- Cameras ----

@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return db.query(Camera).filter(Camera.active == True).all()  # noqa: E712


@router.post("/cameras", response_model=CameraOut)
def create_camera(payload: CameraIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if payload.source_type not in ("mp4", "webcam", "rtsp"):
        raise HTTPException(400, "source_type must be mp4, webcam, or rtsp")
    cam = Camera(**payload.model_dump())
    db.add(cam)
    db.commit()
    db.refresh(cam)
    chain.append(db, actor=user.username, action="camera_created", details={"camera_id": cam.id, "name": cam.name})
    source_manager.start_camera(cam)
    return cam


@router.put("/cameras/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: str, payload: CameraIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if payload.source_type not in ("mp4", "webcam", "rtsp"):
        raise HTTPException(400, "source_type must be mp4, webcam, or rtsp")
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    for k, v in payload.model_dump().items():
        setattr(cam, k, v)
    db.commit()
    db.refresh(cam)
    chain.append(db, actor=user.username, action="camera_updated", details={"camera_id": cam.id})
    if cam.active:
        source_manager.start_camera(cam)  # restart with new source settings
    # a retired camera's config can still be edited (e.g. fixing a URI before
    # reactivating), but must not spin up a live worker -- that would break
    # the "retired cameras don't capture" invariant delete_camera relies on
    return cam


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    # Soft delete: a camera's past observations/incidents/evidence are audit-relevant
    # and must not be destroyed, so we retire it (stop capture, hide from active
    # views) rather than hard-deleting the row. See incident/graph.py for the
    # camera-health incident auto-resolution this triggers.
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    if not cam.active:
        raise HTTPException(400, "Camera is already retired")

    source_manager.stop_camera(camera_id)
    cam.active = False
    cam.status = CameraStatus.retired.value
    db.commit()
    db.refresh(cam)

    resolve_camera_health_incidents(db, cam)

    chain.append(db, actor=user.username, action="camera_retired", details={"camera_id": camera_id, "name": cam.name})
    return {"ok": True}


@router.get("/cameras/retired", response_model=list[CameraOut])
def list_retired_cameras(db: Session = Depends(get_db), user=Depends(require_admin)):
    return db.query(Camera).filter(Camera.active == False).all()  # noqa: E712


@router.post("/cameras/{camera_id}/reactivate", response_model=CameraOut)
def reactivate_camera(camera_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    if cam.active:
        raise HTTPException(400, "Camera is already active")

    cam.active = True
    cam.status = CameraStatus.starting.value
    cam.consecutive_failures = 0
    db.commit()
    db.refresh(cam)

    source_manager.start_camera(cam)

    chain.append(db, actor=user.username, action="camera_reactivated", details={"camera_id": camera_id, "name": cam.name})
    return cam


# ---- Zones ----

@router.get("/zones", response_model=list[ZoneOut])
def list_zones(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return [_zone_out(z) for z in db.query(Zone).all()]


@router.post("/zones", response_model=ZoneOut)
def create_zone(payload: ZoneIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if not db.query(Camera).filter(Camera.id == payload.camera_id).first():
        raise HTTPException(404, "Camera not found")
    zone = Zone(
        camera_id=payload.camera_id,
        name=payload.name,
        polygon_json=json.dumps(payload.polygon),
        restricted=payload.restricted,
        loitering_threshold_s=payload.loitering_threshold_s,
        after_hours_monitored=payload.after_hours_monitored,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    chain.append(db, actor=user.username, action="zone_created", details={"zone_id": zone.id, "name": zone.name})
    return _zone_out(zone)


@router.put("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: str, payload: ZoneIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, "Zone not found")
    zone.camera_id = payload.camera_id
    zone.name = payload.name
    zone.polygon_json = json.dumps(payload.polygon)
    zone.restricted = payload.restricted
    zone.loitering_threshold_s = payload.loitering_threshold_s
    zone.after_hours_monitored = payload.after_hours_monitored
    db.commit()
    db.refresh(zone)
    chain.append(db, actor=user.username, action="zone_updated", details={"zone_id": zone.id})
    return _zone_out(zone)


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    # Past observations/incidents that reference this zone are audit-relevant and
    # must not be destroyed (their explanation text already has the zone name
    # baked in, so they stay meaningful) -- unlink them rather than blocking the
    # delete on the same foreign-key constraint that broke camera deletion.
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, "Zone not found")

    db.query(Observation).filter(Observation.zone_id == zone_id).update({"zone_id": None})
    db.query(Incident).filter(Incident.zone_id == zone_id).update({"zone_id": None})
    db.query(AccessEvent).filter(AccessEvent.zone_id == zone_id).update({"zone_id": None})
    db.query(Schedule).filter(Schedule.scope == "zone", Schedule.scope_id == zone_id).delete()

    db.delete(zone)
    db.commit()
    chain.append(db, actor=user.username, action="zone_deleted", details={"zone_id": zone_id, "name": zone.name})
    return {"ok": True}


# ---- Schedules ----

@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return [_schedule_out(s) for s in db.query(Schedule).all()]


@router.post("/schedules", response_model=ScheduleOut)
def create_schedule(payload: ScheduleIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    sched = Schedule(
        scope=payload.scope,
        scope_id=payload.scope_id,
        business_hours_json=json.dumps(payload.business_hours),
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    chain.append(db, actor=user.username, action="schedule_created", details={"schedule_id": sched.id})
    return _schedule_out(sched)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: str, payload: ScheduleIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(404, "Schedule not found")
    sched.scope = payload.scope
    sched.scope_id = payload.scope_id
    sched.business_hours_json = json.dumps(payload.business_hours)
    db.commit()
    db.refresh(sched)
    chain.append(db, actor=user.username, action="schedule_updated", details={"schedule_id": sched.id})
    return _schedule_out(sched)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(404, "Schedule not found")
    db.delete(sched)
    db.commit()
    chain.append(db, actor=user.username, action="schedule_deleted", details={"schedule_id": schedule_id})
    return {"ok": True}


# ---- SOPs ----

@router.get("/sops", response_model=list[SOPOut])
def list_sops(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    return db.query(SOP).all()


@router.post("/sops", response_model=SOPOut)
def create_sop(payload: SOPIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    sop = SOP(**payload.model_dump())
    db.add(sop)
    db.commit()
    db.refresh(sop)
    chain.append(db, actor=user.username, action="sop_created", details={"sop_id": sop.id, "incident_type": sop.incident_type})
    return sop


@router.put("/sops/{sop_id}", response_model=SOPOut)
def update_sop(sop_id: str, payload: SOPIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")
    for k, v in payload.model_dump().items():
        setattr(sop, k, v)
    db.commit()
    db.refresh(sop)
    chain.append(db, actor=user.username, action="sop_updated", details={"sop_id": sop.id})
    return sop


@router.delete("/sops/{sop_id}")
def delete_sop(sop_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")
    db.delete(sop)
    db.commit()
    chain.append(db, actor=user.username, action="sop_deleted", details={"sop_id": sop_id})
    return {"ok": True}
