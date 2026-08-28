import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.access_sim.simulator import generator as access_event_generator
from app.config import FRONTEND_DIST_DIR
from app.db import Base, SessionLocal, engine, run_light_migrations
from app.incident import graph as incident_graph
from app.ingestion.event_bus import event_bus
from app.ingestion.source_manager import source_manager
from app.models import Camera
from app.routers import (
    access as access_router,
    audit as audit_router,
    auth,
    config as config_router,
    evidence as evidence_router,
    incidents as incidents_router,
    observations as observations_router,
    passport as passport_router,
    replay as replay_router,
    stream as stream_router,
    ws as ws_router,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cctv")

Base.metadata.create_all(bind=engine)
run_light_migrations()

app = FastAPI(title="Campus CCTV Feed Analyzer")

# Allows `npm run dev` (Vite on :5173) to talk to the API during frontend development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(config_router.router)
app.include_router(audit_router.router)
app.include_router(passport_router.router)
app.include_router(stream_router.router)
app.include_router(observations_router.router)
app.include_router(incidents_router.router)
app.include_router(evidence_router.router)
app.include_router(access_router.router)
app.include_router(replay_router.router)
app.include_router(ws_router.router)


@app.on_event("startup")
async def on_startup():
    logger.info("Campus CCTV Feed Analyzer backend starting up")

    # Every sync `def` route (config/incidents/observations/access/passport)
    # and each long-lived MJPEG stream generator (stream.py) share this same
    # threadpool. A handful of open camera-tile streams can otherwise occupy
    # the whole default budget (40) for their entire connection lifetime and
    # starve unrelated, cheap DB-read endpoints. Headroom for 3+ simultaneous
    # streams plus normal API traffic.
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = 100

    event_bus.on_observation = incident_graph.ingest_observation
    event_bus.on_camera_status = incident_graph.ingest_camera_health
    event_bus.on_scene_warning = incident_graph.ingest_scene_warning
    event_bus.bind_loop(asyncio.get_event_loop(), ws_router.broadcast_queue)
    event_bus.start()
    asyncio.create_task(ws_router.fanout_loop())

    db = SessionLocal()
    try:
        cameras = db.query(Camera).filter(Camera.active == True).all()  # noqa: E712
    finally:
        db.close()
    source_manager.start_all(cameras)
    logger.info("Started %d camera worker(s)", len(cameras))

    access_event_generator.start()


@app.on_event("shutdown")
def on_shutdown():
    source_manager.stop_all()
    event_bus.stop()
    access_event_generator.stop()


if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # index.html (and its fallback for client-side routes) must never be
        # cached -- it's what points the browser at the current build's
        # content-hashed JS/CSS filenames. A stale cached copy keeps loading
        # an old JS bundle indefinitely after a redeploy.
        no_cache = {"Cache-Control": "no-cache, no-store, must-revalidate"}
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate, headers=no_cache)
        return FileResponse(FRONTEND_DIST_DIR / "index.html", headers=no_cache)
