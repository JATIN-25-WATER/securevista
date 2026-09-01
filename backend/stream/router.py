"""
backend/stream/router.py

MJPEG streaming endpoint.

GET /stream/{camera_id}
  — streams annotated frames as multipart/x-mixed-replace MJPEG
  — requires valid JWT (query param ?token= OR Authorization header)
  — returns 404 if camera doesn't exist, 503 if source not running

Browser usage:
  <img src="/stream/1?token=<jwt>" />

Privacy: face blurring happens here if BLUR_FACES env var is set.
No face data is stored; blurring is purely display-layer.
"""
import asyncio
import logging
import os
from typing import AsyncGenerator

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.auth.jwt import decode_token
from backend.db.database import get_db
from backend.db.models import Camera
from backend.pipeline.source_manager import SourceManager, get_source_manager
from backend.modules.face_processor import FaceProcessor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])

BLUR_FACES = os.getenv("BLUR_FACES", "true").lower() == "true"
JPEG_QUALITY = int(os.getenv("STREAM_JPEG_QUALITY", "75"))
STREAM_FPS = float(os.getenv("STREAM_FPS", "15"))

_face_processor = FaceProcessor() if BLUR_FACES else None


# ── Stream endpoint ───────────────────────────────────────────────────────────

@router.get("/{camera_id}")
async def mjpeg_stream(
    camera_id: int,
    token: str = Query(..., description="JWT access token"),
    db: Session = Depends(get_db),
    source_mgr: SourceManager = Depends(get_source_manager),
):
    """
    MJPEG stream for a single camera.
    Auth via ?token= query param (required for <img> tags in browsers).
    """
    # Auth: validate token from query param
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    role = payload.get("role", "")
    if role not in ("admin", "operator", "responder"):
        raise HTTPException(status_code=403, detail="Insufficient role")

    # Camera must exist in DB
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if cam is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    src = source_mgr.get(camera_id)
    if src is None:
        raise HTTPException(
            status_code=503,
            detail=f"Camera {camera_id} source not registered. Start it first via POST /cameras/{camera_id}/start",
        )

    return StreamingResponse(
        _frame_generator(src, camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Camera-Id": str(camera_id),
        },
    )


async def _frame_generator(src, camera_id: int) -> AsyncGenerator[bytes, None]:
    """Async generator: yields MJPEG frames until client disconnects."""
    interval = 1.0 / STREAM_FPS
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

    consecutive_empty = 0

    while True:
        await asyncio.sleep(interval)

        frame = src.get_annotated_frame()

        if frame is None:
            consecutive_empty += 1
            if consecutive_empty > 100:
                # Source dead — send placeholder and exit
                yield _offline_frame(camera_id, encode_params)
                break
            yield _offline_frame(camera_id, encode_params)
            continue

        consecutive_empty = 0

        # Optional face blur (display layer only — no face data stored)
        if BLUR_FACES and _face_processor is not None:
            try:
                frame, _ = _face_processor.process_faces(frame, blur_faces=True)
            except Exception:
                pass

        ret, jpeg = cv2.imencode(".jpg", frame, encode_params)
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg.tobytes()
            + b"\r\n"
        )


def _offline_frame(camera_id: int, encode_params: list) -> bytes:
    """Return a dark placeholder JPEG when camera is offline."""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.putText(
        frame,
        f"Camera {camera_id} — No Signal",
        (400, 360),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (80, 80, 80),
        2,
        cv2.LINE_AA,
    )
    _, jpeg = cv2.imencode(".jpg", frame, encode_params)
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        + jpeg.tobytes()
        + b"\r\n"
    )
