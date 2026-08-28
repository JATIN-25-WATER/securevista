"""Versioned, privacy-safe observation schema.

Version 1: geometry + anonymous per-camera track id only. No imagery, no
biometric features, no cross-camera identity. Any future breaking change
to this shape must bump SCHEMA_VERSION and add observation_v2.py rather
than mutating this one, so historical observations stay self-describing.
"""
from datetime import datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class ObservationV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    camera_id: str
    zone_id: str | None = None
    track_id: int = Field(..., description="Anonymous, camera-local tracking id. Never reused across cameras.")
    ts: datetime
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="[x1,y1,x2,y2] normalized 0-1")
    event_type: str
    confidence: float

    class Config:
        from_attributes = True
