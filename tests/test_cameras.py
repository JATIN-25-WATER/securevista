"""
tests/test_cameras.py
Phase 2 tests: cameras CRUD and pipeline control endpoints.
Run with: pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock, patch

from backend.main import app
from backend.db.database import Base, get_db
from backend.db.seed import seed_database
from backend.pipeline.source_manager import get_source_manager, SourceManager
from backend.pipeline.pipeline_manager import get_pipeline_manager, PipelineManager

# ── Test DB setup ─────────────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///file:mem_cameras?mode=memory&cache=shared"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False, "uri": True},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    seed_database(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Mock SourceManager + PipelineManager (no real video needed) ───────────────

mock_source_mgr = MagicMock(spec=SourceManager)
mock_pipeline_mgr = MagicMock(spec=PipelineManager)

# Simulate successful source start
mock_source = MagicMock()
mock_source.status_dict.return_value = {
    "camera_id": 1,
    "source_uri": "test.mp4",
    "state": "active",
    "fps": 29.0,
    "last_frame": None,
    "pipeline": True,
}
mock_source_mgr.get.return_value = mock_source
mock_source_mgr.start.return_value = True
mock_pipeline_mgr.get.return_value = MagicMock()
mock_pipeline_mgr.running_ids.return_value = [1]


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_source_manager] = lambda: mock_source_mgr
app.dependency_overrides[get_pipeline_manager] = lambda: mock_pipeline_mgr

client = TestClient(app)


# ── Auth helper ───────────────────────────────────────────────────────────────

def admin_token() -> str:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


def operator_token() -> str:
    r = client.post("/auth/login", json={"username": "operator", "password": "op123"})
    return r.json()["access_token"]


def responder_token() -> str:
    r = client.post("/auth/login", json={"username": "responder", "password": "resp123"})
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── List cameras ─────────────────────────────────────────────────────────────

def test_list_cameras_admin():
    resp = client.get("/cameras", headers=auth(admin_token()))
    assert resp.status_code == 200
    cameras = resp.json()
    assert isinstance(cameras, list)
    assert len(cameras) == 3  # seeded cameras


def test_list_cameras_operator():
    resp = client.get("/cameras", headers=auth(operator_token()))
    assert resp.status_code == 200


def test_list_cameras_responder_forbidden():
    resp = client.get("/cameras", headers=auth(responder_token()))
    assert resp.status_code == 403


def test_list_cameras_unauthenticated():
    resp = client.get("/cameras")
    assert resp.status_code == 403  # HTTPBearer raises 403 on missing creds


# ── Get single camera ─────────────────────────────────────────────────────────

def test_get_camera_exists():
    resp = client.get("/cameras/1", headers=auth(admin_token()))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "source_uri" in data


def test_get_camera_not_found():
    resp = client.get("/cameras/9999", headers=auth(admin_token()))
    assert resp.status_code == 404


# ── Create camera ─────────────────────────────────────────────────────────────

def test_create_camera_admin():
    resp = client.post(
        "/cameras",
        json={"name": "New Cam", "source_uri": "newcam.mp4"},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Cam"
    assert data["source_uri"] == "newcam.mp4"
    assert data["status"] == "unknown"
    mock_source_mgr.add.assert_called()


def test_create_camera_operator_forbidden():
    resp = client.post(
        "/cameras",
        json={"name": "X", "source_uri": "x.mp4"},
        headers=auth(operator_token()),
    )
    assert resp.status_code == 403


# ── Update camera ─────────────────────────────────────────────────────────────

def test_update_camera_name():
    resp = client.patch(
        "/cameras/1",
        json={"name": "Renamed Cam"},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Cam"


def test_update_camera_uri_triggers_restart():
    mock_source_mgr.reset_mock()
    resp = client.patch(
        "/cameras/1",
        json={"source_uri": "new_source.mp4"},
        headers=auth(admin_token()),
    )
    assert resp.status_code == 200
    mock_source_mgr.remove.assert_called_with(1)
    mock_source_mgr.add.assert_called()


# ── Delete camera ─────────────────────────────────────────────────────────────

def test_delete_camera():
    # Create one to delete
    create = client.post(
        "/cameras",
        json={"name": "ToDelete", "source_uri": "del.mp4"},
        headers=auth(admin_token()),
    )
    cam_id = create.json()["id"]
    resp = client.delete(f"/cameras/{cam_id}", headers=auth(admin_token()))
    assert resp.status_code == 204

    # Gone
    resp2 = client.get(f"/cameras/{cam_id}", headers=auth(admin_token()))
    assert resp2.status_code == 404


def test_delete_camera_operator_forbidden():
    resp = client.delete("/cameras/1", headers=auth(operator_token()))
    assert resp.status_code == 403


# ── Start / stop pipeline ─────────────────────────────────────────────────────

def test_start_camera():
    mock_source_mgr.start.return_value = True
    resp = client.post("/cameras/1/start", headers=auth(admin_token()))
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_start_camera_source_fail():
    mock_source_mgr.start.return_value = False
    resp = client.post("/cameras/1/start", headers=auth(admin_token()))
    assert resp.status_code == 503
    mock_source_mgr.start.return_value = True  # reset


def test_stop_camera():
    resp = client.post("/cameras/1/stop", headers=auth(admin_token()))
    assert resp.status_code == 200
    assert resp.json()["status"] == "offline"


def test_start_stop_operator_allowed():
    resp_start = client.post("/cameras/1/start", headers=auth(operator_token()))
    assert resp_start.status_code == 200
    resp_stop = client.post("/cameras/1/stop", headers=auth(operator_token()))
    assert resp_stop.status_code == 200


def test_start_stop_responder_forbidden():
    resp = client.post("/cameras/1/start", headers=auth(responder_token()))
    assert resp.status_code == 403


# ── Camera status ─────────────────────────────────────────────────────────────

def test_camera_status():
    resp = client.get("/cameras/1/status", headers=auth(admin_token()))
    assert resp.status_code == 200
    data = resp.json()
    assert "state" in data


def test_camera_status_not_registered():
    mock_source_mgr.get.return_value = None
    resp = client.get("/cameras/1/status", headers=auth(admin_token()))
    assert resp.status_code == 200
    assert resp.json()["state"] == "unregistered"
    mock_source_mgr.get.return_value = mock_source  # reset


# ── Observations ──────────────────────────────────────────────────────────────

def test_list_observations_empty():
    resp = client.get("/cameras/1/observations", headers=auth(admin_token()))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_observations_responder_allowed():
    resp = client.get("/cameras/1/observations", headers=auth(responder_token()))
    assert resp.status_code == 200
