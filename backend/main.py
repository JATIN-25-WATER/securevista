"""
backend/main.py
FastAPI application entry point.
Starts the DB, seeds default data, and mounts all routers.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from alembic import command
from alembic.config import Config

from backend.db.database import SessionLocal
from backend.db.seed import seed_database
from backend.auth.router import router as auth_router
from backend.cameras.router import router as cameras_router
from backend.stream.router import router as stream_router
from backend.zones.router import router as zones_router
from backend.incidents.router import router as incidents_router
from backend.evidence.router import router as evidence_router
from backend.audit.router import router as audit_router
from backend.pipeline.source_manager import get_source_manager
from backend.pipeline.pipeline_manager import get_pipeline_manager
from backend.db.models import Camera

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (replaces deprecated @app.on_event) ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Running database migrations...")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    logger.info("Running database seed...")
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    # Register all existing cameras in SourceManager (don't auto-start — operator does that)
    source_mgr = get_source_manager()
    db = SessionLocal()
    try:
        cameras = db.query(Camera).all()
        for cam in cameras:
            source_mgr.add(camera_id=cam.id, source_uri=cam.source_uri)
        logger.info("Registered %d cameras in SourceManager", len(cameras))
    finally:
        db.close()

    logger.info("SecureVista backend ready.")
    yield

    # Shutdown — stop all pipelines and sources cleanly
    logger.info("SecureVista backend shutting down.")
    get_pipeline_manager().detach_all()
    get_source_manager().stop_all()


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SecureVista API",
    description="AI-augmented campus security surveillance system",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In production, restrict origins to the actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(cameras_router)   # Phase 2
app.include_router(stream_router)    # Phase 2
app.include_router(zones_router)     # Phase 3
app.include_router(incidents_router) # Phase 3
app.include_router(evidence_router)  # Phase 3
app.include_router(audit_router)     # Phase 3


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
def health():
    """Liveness probe — returns ok when server is up."""
    return {"status": "ok", "version": "1.0.0"}
