"""Pre/post-event evidence clip assembly, redaction, hashing, and signing."""
import logging
import time
import uuid

import cv2
import numpy as np

from app.config import CLIPS_DIR, POST_EVENT_CAPTURE_SECONDS, PREVIEWS_DIR
from app.evidence.redact import apply_redaction
from app.evidence.sign import sha256_file, sign_digest
from app.ingestion.source_manager import source_manager
from app.models import EvidencePackage, Incident

logger = logging.getLogger("cctv.evidence")

CAPTURE_POLL_INTERVAL_S = 0.2


def _poll_post_event_frames(camera_id: str, seconds: float) -> list[tuple[float, bytes, list]]:
    frames = []
    end_at = time.time() + seconds
    while time.time() < end_at:
        jpeg, boxes = source_manager.get_frame_and_boxes(camera_id)
        if jpeg is not None:
            frames.append((time.time(), jpeg, boxes))
        time.sleep(CAPTURE_POLL_INTERVAL_S)
    return frames


def _decode(jpeg_bytes: bytes):
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _write_clips(frames: list[tuple[float, bytes, list]], clip_path, preview_path, fps: float = 5.0) -> bool:
    """Writes the raw and redacted-preview clips in a single pass: each JPEG
    is decoded once (previously each was decoded twice, once per clip), and
    the target frame size is taken from the first frame that actually
    decodes rather than always frames[0] -- one corrupt/truncated frame at
    the start of the buffer no longer aborts the whole capture when later
    frames are fine."""
    decoded = []
    for _, jpeg_bytes, boxes in frames:
        frame = _decode(jpeg_bytes)
        if frame is not None:
            decoded.append((frame, boxes))
    if not decoded:
        return False

    h, w = decoded[0][0].shape[:2]
    clip_writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    preview_writer = cv2.VideoWriter(str(preview_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        for frame, boxes in decoded:
            if frame.shape[:2] != (h, w):
                frame = cv2.resize(frame, (w, h))
            clip_writer.write(frame)
            apply_redaction(frame, boxes)  # mutates in place -- raw frame is already written above
            preview_writer.write(frame)
    finally:
        clip_writer.release()
        preview_writer.release()
    return True


def create_evidence_package(db, incident: Incident) -> EvidencePackage:
    if not incident.camera_id:
        raise ValueError("Incident has no associated camera; cannot capture evidence")

    buffer = source_manager.get_buffer(incident.camera_id)
    pre_event = buffer.snapshot() if buffer else []
    post_event = _poll_post_event_frames(incident.camera_id, POST_EVENT_CAPTURE_SECONDS)
    frames = sorted(pre_event + post_event, key=lambda item: item[0])

    evidence_id = uuid.uuid4().hex
    clip_path = CLIPS_DIR / f"{evidence_id}.mp4"
    preview_path = PREVIEWS_DIR / f"{evidence_id}.mp4"

    if not _write_clips(frames, clip_path, preview_path):
        raise RuntimeError("No frames available to build evidence clip")

    digest = sha256_file(clip_path)
    signature = sign_digest(digest)

    package = EvidencePackage(
        id=evidence_id,
        incident_id=incident.id,
        clip_path=str(clip_path),
        redacted_preview_path=str(preview_path),
        sha256=digest,
        signature=signature,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package
