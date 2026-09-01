"""
tests/test_alerts.py
Tests for real-time alert listing, WebSocket connection, and alert acknowledgement.
"""
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.db.database import Base, get_db
from backend.db.models import User, Camera, Observation, Zone, Schedule, Incident, AuditLog, EvidencePackage
from backend.db.seed import seed_database

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    seed_database(db)
    cam = db.query(Camera).first()
    if cam:
        obs = Observation(
            camera_id=cam.id,
            track_id="test-1",
            event_type="restricted_zone_entry",
            timestamp=datetime.utcnow(),
            confidence_score=0.95,
            impact_score=0.9,
            explanation="Person entered restricted area in test",
        )
        db.add(obs)
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_list_alerts_unauthenticated():
    response = client.get("/alerts")
    assert response.status_code in (401, 403)


def test_list_alerts_authenticated():
    login = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    response = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    alerts = response.json()
    assert isinstance(alerts, list)
    assert len(alerts) >= 1
    assert alerts[0]["event_type"] == "restricted_zone_entry"


def test_acknowledge_alert():
    login = client.post("/auth/login", json={"username": "operator", "password": "op123"})
    token = login.json()["access_token"]
    
    alerts_res = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
    alert_id = alerts_res.json()[0]["id"]

    ack_res = client.post(f"/alerts/{alert_id}/acknowledge", headers={"Authorization": f"Bearer {token}"})
    assert ack_res.status_code == 200
    data = ack_res.json()
    assert data["status"] == "acknowledged"
    assert data["acknowledged_by"] == "operator"

    alerts_updated = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
    for a in alerts_updated.json():
        if a["id"] == alert_id:
            assert a["acknowledged"] is True
            assert a["acknowledged_by_username"] == "operator"


def test_websocket_alerts_unauthenticated():
    with pytest.raises(Exception):
        with client.websocket_connect("/alerts/ws") as websocket:
            websocket.receive_text()


def test_websocket_alerts_authenticated():
    login = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    with client.websocket_connect(f"/alerts/ws?token={token}") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert data == "pong"
