import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audit import chain
from app.db import Base
from app.models import AuditLog  # noqa: F401 -- ensures the table is registered on Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_fresh_chain_verifies(db_session):
    chain.append(db_session, actor="system", action="login_success", details={"role": "admin"})
    chain.append(db_session, actor="system", action="incident_created", details={"incident_id": "abc"})
    result = chain.verify_chain(db_session)
    assert result == {"valid": True, "total_entries": 2, "broken_at_id": None}


def test_tampering_with_a_row_breaks_verification(db_session):
    chain.append(db_session, actor="system", action="login_success", details={"role": "admin"})
    entry = chain.append(db_session, actor="system", action="incident_created", details={"incident_id": "abc"})
    chain.append(db_session, actor="system", action="incident_resolved", details={"incident_id": "abc"})

    entry.details_json = '{"incident_id": "TAMPERED"}'
    db_session.commit()

    result = chain.verify_chain(db_session)
    assert result["valid"] is False
    assert result["broken_at_id"] == entry.id
