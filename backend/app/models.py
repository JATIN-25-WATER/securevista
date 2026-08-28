import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db import Base


def _uid() -> str:
    return uuid.uuid4().hex


class SourceType(str, enum.Enum):
    mp4 = "mp4"
    webcam = "webcam"
    rtsp = "rtsp"


class CameraStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    frozen = "frozen"
    blackout = "blackout"
    blurred = "blurred"
    starting = "starting"
    retired = "retired"


class IncidentStatus(str, enum.Enum):
    new = "new"
    acknowledged = "acknowledged"
    investigating = "investigating"
    escalated = "escalated"
    resolved = "resolved"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uid)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | operator | supervisor
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True, default=_uid)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # mp4 | webcam | rtsp
    uri = Column(String, nullable=False)
    loop = Column(Boolean, default=True)  # loop mp4 sources to behave like a live feed
    status = Column(String, default=CameraStatus.starting.value)
    last_frame_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    active = Column(Boolean, default=True, nullable=False)

    zones = relationship("Zone", back_populates="camera", cascade="all, delete-orphan")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String, primary_key=True, default=_uid)
    camera_id = Column(String, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    polygon_json = Column(Text, nullable=False)  # JSON list of [x,y] points, normalized 0-1
    restricted = Column(Boolean, default=False)
    loitering_threshold_s = Column(Integer, default=30)
    after_hours_monitored = Column(Boolean, default=True)

    camera = relationship("Camera", back_populates="zones")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(String, primary_key=True, default=_uid)
    scope = Column(String, nullable=False)  # "camera" | "zone"
    scope_id = Column(String, nullable=False)
    business_hours_json = Column(Text, nullable=False)  # {"mon": [["08:00","18:00"]], ...}


class SOP(Base):
    __tablename__ = "sops"

    id = Column(String, primary_key=True, default=_uid)
    incident_type = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    steps_text = Column(Text, nullable=False)


class Observation(Base):
    """Append-only, privacy-safe detection record. This IS the versioned observation schema:
    no imagery, no biometric data, only geometry + an anonymous per-camera track id."""

    __tablename__ = "observations"

    id = Column(String, primary_key=True, default=_uid)
    schema_version = Column(Integer, nullable=False, default=1)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True, index=True)
    track_id = Column(Integer, nullable=False)  # anonymous, camera-local only
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    bbox_json = Column(Text, nullable=False)  # [x1,y1,x2,y2] normalized 0-1
    event_type = Column(String, nullable=False)  # presence | restricted_entry | after_hours | loitering
    confidence = Column(Float, nullable=False)


class AccessEvent(Base):
    """Simulated authorization/access-control event, used to correlate against zone entries."""

    __tablename__ = "access_events"

    id = Column(String, primary_key=True, default=_uid)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    badge_token = Column(String, nullable=False)  # opaque anonymous token, not a real identity
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    simulated = Column(Boolean, default=True)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, default=_uid)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False, default=IncidentStatus.new.value)
    dedup_key = Column(String, nullable=False, index=True)
    impact_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    explanation_json = Column(Text, nullable=False)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # Set by a responder at resolve time: true_positive | false_positive | uncertain | null (undecided).
    # Backs the false-positive analytics view -- never set automatically.
    disposition = Column(String, nullable=True)

    events = relationship("IncidentEvent", back_populates="incident", cascade="all, delete-orphan")
    evidence = relationship("EvidencePackage", back_populates="incident", cascade="all, delete-orphan")


class IncidentObservation(Base):
    __tablename__ = "incident_observations"

    id = Column(String, primary_key=True, default=_uid)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_id = Column(String, ForeignKey("observations.id"), nullable=False)

    __table_args__ = (UniqueConstraint("incident_id", "observation_id", name="uq_incident_observation"),)


class SceneWarning(Base):
    """Heuristic, non-ML-classified scene-level warning (abandoned object,
    visual fire/smoke cue) that is NOT tied to any tracked person -- unlike
    Observation, there is no anonymous track id here at all. These are
    classical-CV heuristics (background subtraction, color/motion), not
    trained classifiers, and are explicitly lower-confidence than
    person-based observations (see incident/scoring.py's confidence cap)."""

    __tablename__ = "scene_warnings"

    id = Column(String, primary_key=True, default=_uid)
    schema_version = Column(Integer, nullable=False, default=1)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True, index=True)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    bbox_json = Column(Text, nullable=False)  # [x1,y1,x2,y2] normalized 0-1
    warning_type = Column(String, nullable=False)  # abandoned_object | fire_smoke
    confidence = Column(Float, nullable=False)


class IncidentSceneWarning(Base):
    __tablename__ = "incident_scene_warnings"

    id = Column(String, primary_key=True, default=_uid)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_warning_id = Column(String, ForeignKey("scene_warnings.id"), nullable=False)

    __table_args__ = (UniqueConstraint("incident_id", "scene_warning_id", name="uq_incident_scene_warning"),)


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(String, primary_key=True, default=_uid)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # created | acknowledged | investigating | escalated | resolved | note
    ts = Column(DateTime(timezone=True), server_default=func.now())
    note = Column(Text, nullable=True)

    incident = relationship("Incident", back_populates="events")


class EvidencePackage(Base):
    __tablename__ = "evidence_packages"

    id = Column(String, primary_key=True, default=_uid)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    clip_path = Column(String, nullable=False)
    redacted_preview_path = Column(String, nullable=False)
    sha256 = Column(String, nullable=False)
    signature = Column(Text, nullable=False)  # base64 Ed25519 signature over the sha256 digest
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="evidence")


class AuditLog(Base):
    """Hash-chained, append-only security audit trail. Each row's hash covers its own
    content plus the previous row's hash, so any edit/delete breaks the chain."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_iso = Column(String, nullable=False)  # exact ISO-8601 string used in the hash — avoids
    # datetime round-trip drift through SQLite, which would otherwise break chain verification.
    actor = Column(String, nullable=False)  # username, or "system"
    action = Column(String, nullable=False)
    details_json = Column(Text, nullable=False)
    prev_hash = Column(String, nullable=False)
    hash = Column(String, nullable=False)


class ScorecardRun(Base):
    __tablename__ = "scorecard_runs"

    id = Column(String, primary_key=True, default=_uid)
    run_at = Column(DateTime(timezone=True), server_default=func.now())
    scenario_id = Column(String, nullable=False)
    precision = Column(Float, nullable=False)
    recall = Column(Float, nullable=False)
    avg_latency_ms = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
