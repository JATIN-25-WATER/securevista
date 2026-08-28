import time

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.auth.deps import get_current_user_flexible
from app.evidence.redact import apply_redaction
from app.ingestion.source_manager import source_manager

router = APIRouter(prefix="/api/stream", tags=["stream"])


def _maybe_redact(camera_id: str, jpeg_bytes: bytes, blur: bool) -> bytes:
    if not blur:
        return jpeg_bytes
    _, boxes = source_manager.get_frame_and_boxes(camera_id)
    if not boxes:
        return jpeg_bytes
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes
    frame = apply_redaction(frame, boxes)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ok else jpeg_bytes


def _mjpeg_generator(camera_id: str, blur: bool):
    boundary = b"--frame"
    while True:
        frame = source_manager.get_frame(camera_id)
        if frame is not None:
            frame = _maybe_redact(camera_id, frame, blur)
            yield (
                boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.08)


@router.get("/{camera_id}/mjpeg")
def stream_mjpeg(
    camera_id: str,
    blur: bool = Query(False, description="Blur every tracked person on demand, off by default"),
    user=Depends(get_current_user_flexible),
):
    if source_manager.get_frame(camera_id) is None and camera_id not in source_manager.workers:
        raise HTTPException(404, "Camera not running")
    return StreamingResponse(
        _mjpeg_generator(camera_id, blur),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/{camera_id}/snapshot")
def snapshot(
    camera_id: str,
    blur: bool = Query(False, description="Blur every tracked person on demand, off by default"),
    user=Depends(get_current_user_flexible),
):
    frame = source_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(404, "No frame available yet")
    return Response(content=_maybe_redact(camera_id, frame, blur), media_type="image/jpeg")
