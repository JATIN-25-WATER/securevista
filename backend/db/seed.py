"""
backend/db/seed.py
Creates default users, cameras, zones, and schedules if the DB is empty.
Called on FastAPI startup.
"""
import json
import logging
from datetime import datetime
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .models import User, Camera, Zone, Schedule

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def seed_database(db: Session) -> None:
    """Idempotent seed — only runs if users table is empty."""
    if db.query(User).count() > 0:
        logger.info("Database already seeded, skipping.")
        return

    logger.info("Seeding database with default data...")

    # ── Users ──────────────────────────────────────────────────────────────
    users = [
        User(username="admin",     password_hash=hash_password("admin123"),  role="admin"),
        User(username="operator",  password_hash=hash_password("op123"),     role="operator"),
        User(username="responder", password_hash=hash_password("resp123"),   role="responder"),
    ]
    db.add_all(users)
    db.flush()  # Get IDs before adding cameras

    # ── Cameras (pointing to local MP4 test files) ─────────────────────────
    cameras = [
        Camera(name="Main Entrance",   source_uri="test.mp4",  status="unknown"),
        Camera(name="Parking Lot",     source_uri="test1.mp4", status="unknown"),
        Camera(name="Lab Corridor",    source_uri="test3.mp4", status="unknown"),
    ]
    db.add_all(cameras)
    db.flush()

    cam1_id = cameras[0].id

    # ── Zones on Camera 1 ─────────────────────────────────────────────────
    # Polygon points are expressed as fractions of 1280x720 frame
    # These are sample zones — operator reconfigures via UI
    zones = [
        Zone(
            camera_id=cam1_id,
            name="Server Room Door",
            polygon_points=json.dumps([[800, 100], [1100, 100], [1100, 400], [800, 400]]),
            zone_type="restricted",
            risk_level=5,
        ),
        Zone(
            camera_id=cam1_id,
            name="Reception Area",
            polygon_points=json.dumps([[100, 200], [600, 200], [600, 600], [100, 600]]),
            zone_type="monitored",
            risk_level=2,
        ),
    ]
    db.add_all(zones)

    # ── Schedule on Camera 1 (business hours Mon–Fri) ─────────────────────
    schedules = [
        Schedule(
            camera_id=cam1_id,
            name="Business Hours",
            start_time="08:00",
            end_time="18:00",
            days_of_week=json.dumps(["Mon", "Tue", "Wed", "Thu", "Fri"]),
        ),
    ]
    db.add_all(schedules)

    db.commit()
    logger.info(
        f"Seeded: {len(users)} users, {len(cameras)} cameras, "
        f"{len(zones)} zones, {len(schedules)} schedules."
    )
