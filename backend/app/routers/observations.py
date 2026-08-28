import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import any_authenticated
from app.db import get_db
from app.ingestion.source_manager import source_manager
from app.models import Camera, Observation
from app.schemas.observation_v1 import ObservationV1

router = APIRouter(prefix="/api/observations", tags=["observations"])


@router.get("/recent", response_model=list[ObservationV1])
def recent_observations(
    camera_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user=Depends(any_authenticated),
):
    q = db.query(Observation)
    if camera_id:
        q = q.filter(Observation.camera_id == camera_id)
    rows = q.order_by(Observation.ts.desc()).limit(limit).all()
    return [
        ObservationV1(
            id=r.id,
            camera_id=r.camera_id,
            zone_id=r.zone_id,
            track_id=r.track_id,
            ts=r.ts,
            bbox=json.loads(r.bbox_json),
            event_type=r.event_type,
            confidence=r.confidence,
        )
        for r in rows
    ]


@router.get("/live-tracks")
def live_tracks(db: Session = Depends(get_db), user=Depends(any_authenticated)):
    cameras = db.query(Camera).all()
    result = {}
    for cam in cameras:
        worker = source_manager.workers.get(cam.id)
        if not worker:
            result[cam.id] = {"status": cam.status, "tracks": {}}
            continue
        result[cam.id] = {
            "status": worker.state.status,
            "tracks": {
                str(tid): {"bbox": info["bbox"]}
                for tid, info in worker.state.active_tracks.items()
            },
        }
    return result
