import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Camera, Incident, Observation


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _camera_with_history(db_session):
    cam = Camera(name="Main Gate", source_type="mp4", uri="test.mp4")
    db_session.add(cam)
    db_session.commit()

    db_session.add(Observation(
        camera_id=cam.id, track_id=1, bbox_json="[0,0,1,1]", event_type="presence", confidence=0.9,
    ))
    db_session.add(Incident(
        type="camera_offline", status="resolved", dedup_key=f"camera_offline:{cam.id}",
        impact_score=60.0, confidence_score=90.0, explanation_json="{}", camera_id=cam.id,
    ))
    db_session.commit()
    return cam


def test_hard_delete_of_camera_with_history_violates_fk(db_session):
    """Documents the bug: a camera that has produced any observation/incident
    cannot be hard-deleted once foreign_keys=ON (as the real app sets it) --
    this is exactly why delete_camera must soft-delete instead."""
    cam = _camera_with_history(db_session)
    db_session.delete(cam)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_soft_delete_preserves_history_and_hides_camera(db_session):
    cam = _camera_with_history(db_session)

    cam.active = False
    cam.status = "retired"
    db_session.commit()

    active_cameras = db_session.query(Camera).filter(Camera.active == True).all()  # noqa: E712
    assert active_cameras == []

    still_there = db_session.query(Camera).filter(Camera.id == cam.id).first()
    assert still_there is not None
    assert still_there.active is False

    assert db_session.query(Observation).filter(Observation.camera_id == cam.id).count() == 1
    assert db_session.query(Incident).filter(Incident.camera_id == cam.id).count() == 1
