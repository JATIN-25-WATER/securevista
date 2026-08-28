"""Central paths and settings for the Campus CCTV Analyzer backend.

All state lives under backend/data and backend/media so the whole app
is relocatable and runs fully offline after the first model download.
"""
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = BACKEND_DIR / "data"
KEYS_DIR = DATA_DIR / "keys"
MEDIA_DIR = BACKEND_DIR / "media"
CLIPS_DIR = MEDIA_DIR / "clips"
PREVIEWS_DIR = MEDIA_DIR / "previews"
WEIGHTS_DIR = BACKEND_DIR / "weights"
SCENARIO_CLIPS_DIR = BACKEND_DIR / "scenario_clips"
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "app" / "dist"

for d in (DATA_DIR, KEYS_DIR, MEDIA_DIR, CLIPS_DIR, PREVIEWS_DIR, WEIGHTS_DIR, SCENARIO_CLIPS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "app.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

SECRET_KEY_PATH = DATA_DIR / "jwt_secret.key"


def _load_or_create_jwt_secret() -> str:
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    secret = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(secret)
    return secret


JWT_SECRET_KEY = _load_or_create_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 12 * 60

ED25519_PRIVATE_KEY_PATH = KEYS_DIR / "evidence_ed25519_private.pem"
ED25519_PUBLIC_KEY_PATH = KEYS_DIR / "evidence_ed25519_public.pem"

YOLO_MODEL_PATH = WEIGHTS_DIR / "yolov8n.pt"
PERSON_CLASS_ID = 0  # COCO class 0 = person; this system detects the person class only.
DETECTION_CONF_THRESHOLD = 0.45

# Model Passport — static disclosure about the detection model in use.
MODEL_PASSPORT = {
    "model_name": "YOLOv8n (Ultralytics)",
    "model_version": "yolov8n-coco-2023",
    "task": "Person detection only (COCO class 0). No other object classes are used.",
    "training_data": "COCO 2017 (general-purpose, publicly available). No campus-specific fine-tuning has been performed.",
    "tracking": "Anonymous, camera-local centroid tracking. No cross-camera re-identification. No face or biometric processing of any kind.",
    "known_limitations": [
        "Accuracy degrades in low light, heavy occlusion, or extreme camera angles.",
        "Small or distant persons (<~24px bounding box) may be missed.",
        "Tracking IDs are not stable across camera restarts or across cameras.",
        "Not evaluated for crowd counts beyond the scenarios in the scorecard.",
        "Fall/collapse warning is a bounding-box aspect-ratio heuristic, not a trained "
        "or validated fall classifier -- it will misfire on anyone who sits, crouches, "
        "or lies down voluntarily, and its confidence score is hard-capped accordingly.",
        "Abandoned-object warning is classical background subtraction, not an object "
        "classifier -- it cannot identify what an object is, only that a static "
        "non-person blob persisted, and is prone to false positives from lighting "
        "changes or camera vibration.",
        "Fire/smoke visual warning is an HSV color-range heuristic and is the least "
        "reliable signal in this system -- it cannot distinguish real flame from any "
        "other bright orange/red object and its confidence score is capped very low. "
        "It is a visual cue for human review only, never a standalone fire alarm.",
    ],
    "excluded_capabilities": [
        "No facial recognition or identity matching.",
        "No emotion, aggression, or intent inference.",
        "No demographic inference (age, gender, etc).",
        "No individual risk or suspicion scoring.",
    ],
}

ROLES = ("admin", "operator", "supervisor")

# Rolling buffer: how much video history each camera keeps in memory for
# pre-event evidence capture.
ROLLING_BUFFER_SECONDS = 20
POST_EVENT_CAPTURE_SECONDS = 10
DETECTION_TARGET_FPS = 5  # throttle inference so 3 simultaneous sources stay responsive

# The capture loop itself was previously unthrottled: cv2.VideoCapture.read()
# on an mp4 file returns frames as fast as the decoder can produce them (often
# 100+ fps for small SD clips), and every single frame -- not just detection
# ticks -- was running health checks, annotation, JPEG re-encoding, and
# buffer writes. Across 3 simultaneous cameras this pegged multiple CPU cores
# for no visible benefit (nothing consumes frames faster than ~15-20fps
# anyway) and also meant mp4 sources played back much faster than real time,
# which contradicts "staged MP4s behaving like live feeds." Pacing the whole
# loop to this rate fixes both.
STREAM_TARGET_FPS = 15

# Camera health thresholds.
# FROZEN_WINDOW_SECONDS is deliberately long: real static CCTV footage (an
# empty hallway, a quiet gate) can easily go many seconds between any
# meaningful pixel change, so a short window makes normal footage look
# "frozen". Genuinely frozen/stuck feeds stay unchanged far longer than that.
OFFLINE_TIMEOUT_SECONDS = 8
FROZEN_WINDOW_SECONDS = 30
FROZEN_DIFF_THRESHOLD = 0.8  # mean abs pixel diff below this over the window => frozen
BLACKOUT_BRIGHTNESS_THRESHOLD = 12.0  # mean luminance below this => blackout
BLACKOUT_STD_THRESHOLD = 6.0  # near-zero variance also implies blackout/covered
BLUR_LAPLACIAN_THRESHOLD = 40.0  # variance of Laplacian below this => severe blur
