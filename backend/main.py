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

    logger.info("SecureVista backend ready.")
    yield
    # Shutdown (nothing to clean up yet)
    logger.info("SecureVista backend shutting down.")


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
# Phase 2+ routers will be added here as they are built:
# app.include_router(cameras_router)
# app.include_router(incidents_router)
# app.include_router(zones_router)
# app.include_router(stream_router)
# app.include_router(evidence_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
def health():
    """Liveness probe — returns ok when server is up."""
    return {"status": "ok", "version": "1.0.0"}
