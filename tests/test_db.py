"""Phase 1 database tests: schema seed and table existence."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.seed import seed_database
from backend.db.models import User, Camera, Zone, Schedule


TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_database(db)
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_all_tables_exist():
    tables = set(inspect(engine).get_table_names())
    expected = {
        "users",
        "cameras",
        "zones",
        "schedules",
        "observations",
        "incidents",
        "incident_observations",
        "audit_log",
        "evidence_packages",
    }
    assert expected.issubset(tables)


def test_seed_creates_three_users(seeded_db):
    assert seeded_db.query(User).count() == 3
    roles = {u.role for u in seeded_db.query(User).all()}
    assert roles == {"admin", "operator", "responder"}


def test_seed_creates_three_cameras(seeded_db):
    cameras = seeded_db.query(Camera).all()
    assert len(cameras) == 3
    uris = {c.source_uri for c in cameras}
    assert uris == {"test.mp4", "test1.mp4", "test3.mp4"}


def test_seed_creates_zones_and_schedule(seeded_db):
    assert seeded_db.query(Zone).count() == 2
    assert seeded_db.query(Schedule).count() == 1


def test_seed_is_idempotent(seeded_db):
    seed_database(seeded_db)
    assert seeded_db.query(User).count() == 3
