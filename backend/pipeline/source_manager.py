"""
backend/pipeline/source_manager.py

SourceManager is a process-level singleton that owns all VideoSource instances.
It is created once at FastAPI startup and injected via dependency.

Responsibilities:
  - add / remove / start / stop individual sources
  - expose status of all sources
  - ensure clean shutdown on app teardown
"""
import logging
from typing import Dict, Optional

from .video_source import VideoSource, SourceState

logger = logging.getLogger(__name__)


class SourceManager:
    def __init__(self):
        self._sources: Dict[int, VideoSource] = {}  # camera_id → VideoSource

    # ── Source lifecycle ─────────────────────────────────────────────────────

    def add(self, camera_id: int, source_uri: str) -> VideoSource:
        """
        Register a new source. Does NOT start it automatically.
        Replaces existing entry for the same camera_id cleanly.
        """
        if camera_id in self._sources:
            self.stop(camera_id)

        src = VideoSource(camera_id=camera_id, source_uri=source_uri)
        self._sources[camera_id] = src
        logger.info("SourceManager: registered camera %d (%s)", camera_id, source_uri)
        return src

    def remove(self, camera_id: int):
        """Stop and remove a source."""
        if camera_id in self._sources:
            self._sources[camera_id].stop()
            del self._sources[camera_id]
            logger.info("SourceManager: removed camera %d", camera_id)

    def start(self, camera_id: int) -> bool:
        """Start a registered source. Returns True on success."""
        src = self._sources.get(camera_id)
        if src is None:
            logger.error("SourceManager: camera %d not registered", camera_id)
            return False
        return src.start()

    def stop(self, camera_id: int):
        """Stop a running source (keeps it registered)."""
        src = self._sources.get(camera_id)
        if src:
            src.stop()

    def start_all(self):
        """Start every registered source (called at app startup)."""
        for cam_id, src in self._sources.items():
            if src.state == SourceState.IDLE:
                ok = src.start()
                if not ok:
                    logger.warning("SourceManager: camera %d failed to start", cam_id)

    def stop_all(self):
        """Stop every source (called at app shutdown)."""
        for src in self._sources.values():
            src.stop()
        logger.info("SourceManager: all sources stopped")

    # ── Accessors ────────────────────────────────────────────────────────────

    def get(self, camera_id: int) -> Optional[VideoSource]:
        return self._sources.get(camera_id)

    def all_status(self) -> list[dict]:
        return [src.status_dict() for src in self._sources.values()]

    def __len__(self):
        return len(self._sources)


# ── Process-level singleton ─────────────────────────────────────────────────
_manager: Optional[SourceManager] = None


def get_source_manager() -> SourceManager:
    """FastAPI dependency — returns the singleton SourceManager."""
    global _manager
    if _manager is None:
        _manager = SourceManager()
    return _manager
