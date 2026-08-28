"""Idempotent demo seed: 3 role users, 3 staged-MP4 cameras, demo zones,
a default schedule, and starter SOPs. Safe to run multiple times."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.audit import chain
from app.auth.security import hash_password
from app.config import REPO_ROOT
from app.db import Base, SessionLocal, engine
from app.models import SOP, Camera, Schedule, User, Zone

DEMO_USERS = [
    ("admin", "admin123", "admin", "Alex Admin"),
    ("operator", "operator123", "operator", "Olivia Operator"),
    ("supervisor", "supervisor123", "supervisor", "Sam Supervisor"),
]

DEMO_CAMERAS = [
    ("Main Gate", str(REPO_ROOT / "test.mp4")),
    ("Library Court", str(REPO_ROOT / "test1.mp4")),
    ("Rear Loading Dock", str(REPO_ROOT / "test3.mp4")),
]

DEFAULT_BUSINESS_HOURS = {
    day: [["08:00", "20:00"]] for day in ("mon", "tue", "wed", "thu", "fri")
} | {day: [] for day in ("sat", "sun")}

DEFAULT_SOPS = [
    ("restricted_entry", "Restricted Zone Entry", "1. Verify camera feed. 2. Check access log for a matching authorization. 3. If unauthorized, escalate to supervisor. 4. Dispatch responder if zone is high-sensitivity."),
    ("after_hours_presence", "After-Hours Presence", "1. Confirm time against posted schedule. 2. Check access log for authorized after-hours badge. 3. Contact responder for visual confirmation if unresolved."),
    ("loitering", "Loitering", "1. Review dwell duration and zone. 2. Check for legitimate reason (waiting area, queue). 3. Log outcome; escalate only if paired with a restricted-zone or after-hours flag."),
    ("camera_offline", "Camera Offline", "1. Attempt remote reconnect. 2. If unresolved after 3 attempts, dispatch technician. 3. Note blind-spot duration in incident record."),
    ("camera_frozen", "Frozen Feed", "1. Compare against last-known-good frame. 2. Power-cycle the source if remotely possible. 3. Escalate as camera_offline if unresolved."),
    ("camera_blackout", "Camera Blackout / Covered", "1. Treat as potential tamper. 2. Dispatch responder to physically inspect the camera. 3. Escalate to supervisor immediately."),
    ("camera_blur", "Severe Camera Blur", "1. Check for lens obstruction or focus drift. 2. Schedule maintenance if recurring."),
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).first():
            for username, password, role, display_name in DEMO_USERS:
                db.add(User(username=username, password_hash=hash_password(password), role=role, display_name=display_name))
            db.commit()
            chain.append(db, actor="system", action="seed_users", details={"count": len(DEMO_USERS)})
            print("Seeded users:", ", ".join(f"{u}/{p}" for u, p, _, _ in DEMO_USERS))
        else:
            print("Users already exist, skipping user seed.")

        cameras_by_name = {}
        if not db.query(Camera).first():
            for name, uri in DEMO_CAMERAS:
                cam = Camera(name=name, source_type="mp4", uri=uri, loop=True)
                db.add(cam)
                db.flush()
                cameras_by_name[name] = cam
            db.commit()
            chain.append(db, actor="system", action="seed_cameras", details={"count": len(DEMO_CAMERAS)})
            print("Seeded cameras:", ", ".join(DEMO_CAMERAS[i][0] for i in range(len(DEMO_CAMERAS))))
        else:
            print("Cameras already exist, skipping camera seed.")
            cameras_by_name = {c.name: c for c in db.query(Camera).all()}

        if not db.query(Zone).first() and cameras_by_name:
            main_gate = cameras_by_name.get(DEMO_CAMERAS[0][0])
            dock = cameras_by_name.get(DEMO_CAMERAS[2][0])
            if main_gate:
                db.add(Zone(
                    camera_id=main_gate.id,
                    name="Main Gate - Full Frame",
                    polygon_json=json.dumps([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
                    restricted=False,
                    loitering_threshold_s=45,
                ))
            if dock:
                db.add(Zone(
                    camera_id=dock.id,
                    name="Loading Dock - Restricted Area",
                    polygon_json=json.dumps([[0.15, 0.2], [0.85, 0.2], [0.85, 0.9], [0.15, 0.9]]),
                    restricted=True,
                    loitering_threshold_s=20,
                ))
            db.commit()
            chain.append(db, actor="system", action="seed_zones", details={})
            print("Seeded demo zones.")
        else:
            print("Zones already exist or no cameras to attach to, skipping zone seed.")

        if not db.query(Schedule).first() and cameras_by_name:
            for cam in cameras_by_name.values():
                db.add(Schedule(scope="camera", scope_id=cam.id, business_hours_json=json.dumps(DEFAULT_BUSINESS_HOURS)))
            db.commit()
            chain.append(db, actor="system", action="seed_schedules", details={})
            print("Seeded default business-hours schedule for all cameras.")
        else:
            print("Schedules already exist, skipping schedule seed.")

        if not db.query(SOP).first():
            for incident_type, title, steps in DEFAULT_SOPS:
                db.add(SOP(incident_type=incident_type, title=title, steps_text=steps))
            db.commit()
            chain.append(db, actor="system", action="seed_sops", details={"count": len(DEFAULT_SOPS)})
            print("Seeded default SOPs.")
        else:
            print("SOPs already exist, skipping SOP seed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
