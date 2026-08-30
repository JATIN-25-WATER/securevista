"""
tests/test_phase3.py
Phase 3 tests: incidents, zones, audit trail, evidence packages.
Run with: pytest tests/ -v
"""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock, patch
from datetime import datetime

from backend.main import app
from backend.db.database import Base, get_db
from backend.db.seed import seed_database
from backend.db.models import Observation, Incident, IncidentObservation
from backend.pipeline.source_manager import get_source_manager, SourceManager
from backend.pipeline.pipeline_manager import get_pipeline_manager, PipelineManager
from backend.audit.chain import audit_log, verify_chain

# ── Test DB ───────────────────────────────────────────────────────────────────

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
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


mock_source_mgr = MagicMock(spec=SourceManager)
mock_pipeline_mgr = MagicMock(spec=PipelineManager)
mock_pipeline_mgr.get.return_value = None   # no running pipeline in tests

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_source_manager] = lambda: mock_source_mgr
app.dependency_overrides[get_pipeline_manager] = lambda: mock_pipeline_mgr

client = TestClient(app)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _token(username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    return r.json()["access_token"]

def admin_h():  return {"Authorization": f"Bearer {_token('admin','admin123')}"}
def op_h():     return {"Authorization": f"Bearer {_token('operator','op123')}"}
def resp_h():   return {"Authorization": f"Bearer {_token('responder','resp123')}"}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_observation(impact=0.9, event_type="restricted_zone_entry", camera_id=1):
    db = TestingSessionLocal()
    obs = Observation(
        camera_id=camera_id,
        track_id="track_test",
        event_type=event_type,
        timestamp=datetime.utcnow(),
        zone_id=None,
        confidence_score=0.85,
        impact_score=impact,
        explanation="test observation",
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    obs_id = obs.id
    db.close()
    return obs_id


# ══════════════════════════════════════════════════════════════════════════════
# ZONES
# ══════════════════════════════════════════════════════════════════════════════

class TestZones:
    POLYGON = [[10, 10], [200, 10], [200, 200], [10, 200]]

    def test_create_zone_admin(self):
        resp = client.post(
            "/cameras/1/zones",
            json={"name": "Server Room", "polygon_points": self.POLYGON,
                  "zone_type": "restricted", "risk_level": 5},
            headers=admin_h(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["zone_type"] == "restricted"
        assert data["risk_level"] == 5
        assert data["polygon_points"] == self.POLYGON

    def test_create_zone_operator_forbidden(self):
        resp = client.post(
            "/cameras/1/zones",
            json={"name": "X", "polygon_points": self.POLYGON, "zone_type": "safe"},
            headers=op_h(),
        )
        assert resp.status_code == 403

    def test_create_zone_bad_type(self):
        resp = client.post(
            "/cameras/1/zones",
            json={"name": "X", "polygon_points": self.POLYGON, "zone_type": "invisible"},
            headers=admin_h(),
        )
        assert resp.status_code == 422

    def test_create_zone_too_few_points(self):
        resp = client.post(
            "/cameras/1/zones",
            json={"name": "X", "polygon_points": [[0,0],[1,1]], "zone_type": "safe"},
            headers=admin_h(),
        )
        assert resp.status_code == 422

    def test_list_zones(self):
        resp = client.get("/cameras/1/zones", headers=admin_h())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_zone(self):
        create = client.post(
            "/cameras/1/zones",
            json={"name": "Lobby", "polygon_points": self.POLYGON, "zone_type": "monitored"},
            headers=admin_h(),
        )
        zone_id = create.json()["id"]
        resp = client.get(f"/cameras/1/zones/{zone_id}", headers=admin_h())
        assert resp.status_code == 200
        assert resp.json()["name"] == "Lobby"

    def test_update_zone(self):
        create = client.post(
            "/cameras/1/zones",
            json={"name": "Old", "polygon_points": self.POLYGON, "zone_type": "safe"},
            headers=admin_h(),
        )
        zone_id = create.json()["id"]
        resp = client.patch(
            f"/cameras/1/zones/{zone_id}",
            json={"name": "New", "risk_level": 3},
            headers=admin_h(),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"
        assert resp.json()["risk_level"] == 3

    def test_delete_zone(self):
        create = client.post(
            "/cameras/1/zones",
            json={"name": "ToDelete", "polygon_points": self.POLYGON, "zone_type": "safe"},
            headers=admin_h(),
        )
        zone_id = create.json()["id"]
        resp = client.delete(f"/cameras/1/zones/{zone_id}", headers=admin_h())
        assert resp.status_code == 204
        resp2 = client.get(f"/cameras/1/zones/{zone_id}", headers=admin_h())
        assert resp2.status_code == 404

    def test_zone_wrong_camera(self):
        resp = client.get("/cameras/9999/zones", headers=admin_h())
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# INCIDENTS
# ══════════════════════════════════════════════════════════════════════════════

class TestIncidents:

    def test_list_incidents_empty_initially(self):
        resp = client.get("/incidents", headers=admin_h())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_incident_manual(self):
        obs_id = _make_observation()
        resp = client.post(
            "/incidents",
            json={"observation_ids": [obs_id], "note": "manual test"},
            headers=admin_h(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "new"
        assert data["observation_count"] == 1

    def test_create_incident_bad_obs_id(self):
        resp = client.post(
            "/incidents",
            json={"observation_ids": [99999]},
            headers=admin_h(),
        )
        assert resp.status_code == 422

    def test_create_incident_responder_forbidden(self):
        obs_id = _make_observation()
        resp = client.post(
            "/incidents",
            json={"observation_ids": [obs_id]},
            headers=resp_h(),
        )
        assert resp.status_code == 403

    def test_get_incident_with_observations(self):
        obs_id = _make_observation()
        create = client.post(
            "/incidents",
            json={"observation_ids": [obs_id]},
            headers=admin_h(),
        )
        inc_id = create.json()["id"]
        resp = client.get(f"/incidents/{inc_id}", headers=admin_h())
        assert resp.status_code == 200
        data = resp.json()
        assert "observations" in data
        assert len(data["observations"]) == 1

    def test_status_transition_admin(self):
        obs_id = _make_observation()
        create = client.post("/incidents", json={"observation_ids": [obs_id]}, headers=admin_h())
        inc_id = create.json()["id"]

        for new_status in ["acknowledged", "investigating", "resolved"]:
            resp = client.patch(
                f"/incidents/{inc_id}/status",
                json={"new_status": new_status},
                headers=admin_h(),
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == new_status

    def test_resolved_cannot_reopen(self):
        obs_id = _make_observation()
        create = client.post("/incidents", json={"observation_ids": [obs_id]}, headers=admin_h())
        inc_id = create.json()["id"]
        client.patch(f"/incidents/{inc_id}/status", json={"new_status": "resolved"}, headers=admin_h())
        resp = client.patch(f"/incidents/{inc_id}/status", json={"new_status": "new"}, headers=admin_h())
        assert resp.status_code == 409

    def test_responder_limited_transitions(self):
        obs_id = _make_observation()
        create = client.post("/incidents", json={"observation_ids": [obs_id]}, headers=admin_h())
        inc_id = create.json()["id"]

        # responder can acknowledge
        resp = client.patch(f"/incidents/{inc_id}/status",
                            json={"new_status": "acknowledged"}, headers=resp_h())
        assert resp.status_code == 200

        # responder cannot resolve
        resp = client.patch(f"/incidents/{inc_id}/status",
                            json={"new_status": "resolved"}, headers=resp_h())
        assert resp.status_code == 403

    def test_assign_incident(self):
        obs_id = _make_observation()
        create = client.post("/incidents", json={"observation_ids": [obs_id]}, headers=admin_h())
        inc_id = create.json()["id"]

        # Get a valid user id
        db = TestingSessionLocal()
        from backend.db.models import User
        user = db.query(User).first()
        db.close()

        resp = client.post(f"/incidents/{inc_id}/assign",
                           json={"user_id": user.id}, headers=admin_h())
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] == user.id

    def test_list_incidents_filter_by_status(self):
        resp = client.get("/incidents?status=new", headers=admin_h())
        assert resp.status_code == 200
        for inc in resp.json():
            assert inc["status"] == "new"

    def test_get_incident_not_found(self):
        resp = client.get("/incidents/99999", headers=admin_h())
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT CHAIN
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditChain:

    def test_audit_log_writes_entry(self):
        db = TestingSessionLocal()
        entry = audit_log(db, action="test.action", actor_id=1,
                          target_type="camera", target_id=1,
                          payload={"key": "value"})
        assert entry.id is not None
        assert entry.action == "test.action"
        assert entry.prev_hash is not None
        db.close()

    def test_chain_integrity_valid(self):
        db = TestingSessionLocal()
        # Write a few entries
        for i in range(3):
            audit_log(db, action=f"test.chain.{i}", actor_id=1)
        intact, bad_id = verify_chain(db)
        assert intact is True
        assert bad_id is None
        db.close()

    def test_chain_tamper_detection(self):
        from backend.db.models import AuditLog
        db = TestingSessionLocal()
        entry = audit_log(db, action="tamper.test", actor_id=1, payload={"x": 1})

        # Tamper: change the payload without updating the hash
        db.query(AuditLog).filter(AuditLog.id == entry.id).update(
            {"payload": '{"x": 999}'}
        )
        db.commit()

        intact, bad_id = verify_chain(db)
        assert intact is False
        assert bad_id == entry.id
        db.close()

    def test_audit_api_admin_only(self):
        resp_admin = client.get("/audit", headers=admin_h())
        assert resp_admin.status_code == 200

        resp_op = client.get("/audit", headers=op_h())
        assert resp_op.status_code == 403

    def test_audit_verify_endpoint(self):
        resp = client.get("/audit/verify", headers=admin_h())
        assert resp.status_code == 200
        assert "intact" in resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-INCIDENT CORRELATOR
# ══════════════════════════════════════════════════════════════════════════════

class TestCorrelator:

    def test_high_impact_creates_incident(self):
        from backend.incidents.correlator import maybe_create_incident
        db = TestingSessionLocal()

        obs = Observation(
            camera_id=1, track_id="t1", event_type="restricted_zone_entry",
            timestamp=datetime.utcnow(), confidence_score=0.9, impact_score=0.9,
            explanation="test",
        )
        db.add(obs)
        db.commit()
        db.refresh(obs)

        incident = maybe_create_incident(db, obs)
        assert incident is not None
        assert incident.status == "new"
        db.close()

    def test_low_impact_skips_incident(self):
        from backend.incidents.correlator import maybe_create_incident
        db = TestingSessionLocal()

        obs = Observation(
            camera_id=1, track_id="t2", event_type="loitering",
            timestamp=datetime.utcnow(), confidence_score=0.5, impact_score=0.3,
            explanation="low impact",
        )
        db.add(obs)
        db.commit()
        db.refresh(obs)

        incident = maybe_create_incident(db, obs)
        assert incident is None
        db.close()

    def test_dedup_links_to_existing(self):
        from backend.incidents.correlator import maybe_create_incident
        from datetime import timedelta
        db = TestingSessionLocal()

        ts = datetime.utcnow()
        obs1 = Observation(camera_id=2, track_id="t3", event_type="restricted_zone_entry",
                           timestamp=ts, confidence_score=0.9, impact_score=0.9,
                           explanation="first")
        obs2 = Observation(camera_id=2, track_id="t4", event_type="restricted_zone_entry",
                           timestamp=ts + timedelta(seconds=30),  # same 5-min bucket
                           confidence_score=0.9, impact_score=0.9,
                           explanation="second")
        db.add_all([obs1, obs2])
        db.commit()
        db.refresh(obs1)
        db.refresh(obs2)

        inc1 = maybe_create_incident(db, obs1)
        inc2 = maybe_create_incident(db, obs2)

        assert inc1 is not None
        assert inc2 is not None
        assert inc1.id == inc2.id   # same incident, dedup worked
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════

class TestEvidence:

    def _create_incident_with_obs(self):
        obs_id = _make_observation(impact=0.9)
        resp = client.post("/incidents", json={"observation_ids": [obs_id]}, headers=admin_h())
        return resp.json()["id"]

    def test_generate_evidence(self):
        inc_id = self._create_incident_with_obs()
        mock_source_mgr.get.return_value = None   # no live source, use placeholder frames

        resp = client.post(
            f"/incidents/{inc_id}/evidence?padding_seconds=2",
            headers=admin_h(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "manifest_hash" in data
        assert "signature" in data
        assert len(data["manifest_hash"]) == 64   # SHA-256 hex

    def test_list_evidence(self):
        inc_id = self._create_incident_with_obs()
        mock_source_mgr.get.return_value = None

        client.post(f"/incidents/{inc_id}/evidence?padding_seconds=2", headers=admin_h())
        resp = client.get(f"/incidents/{inc_id}/evidence", headers=admin_h())
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_evidence_responder_allowed(self):
        inc_id = self._create_incident_with_obs()
        resp = client.get(f"/incidents/{inc_id}/evidence", headers=resp_h())
        assert resp.status_code == 200

    def test_generate_evidence_responder_forbidden(self):
        inc_id = self._create_incident_with_obs()
        resp = client.post(f"/incidents/{inc_id}/evidence", headers=resp_h())
        assert resp.status_code == 403

    def test_generate_evidence_bad_incident(self):
        resp = client.post("/incidents/99999/evidence", headers=admin_h())
        assert resp.status_code == 404
