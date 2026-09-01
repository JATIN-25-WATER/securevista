"""
backend/pipeline/pipeline_manager.py

PipelineManager maps camera_id → DetectionPipeline.
Works alongside SourceManager: you must have a running VideoSource
before attaching a pipeline.
"""
import logging
from typing import Dict, Optional

from .detection_pipeline import DetectionPipeline
from .video_source import VideoSource

logger = logging.getLogger(__name__)


class PipelineManager:
    def __init__(self):
        self._pipelines: Dict[int, DetectionPipeline] = {}

    def attach(self, source: VideoSource, camera_db_id: int) -> DetectionPipeline:
        """Create and start a DetectionPipeline for the given source."""
        if camera_db_id in self._pipelines:
            self.detach(camera_db_id)

        pipeline = DetectionPipeline(source=source, camera_db_id=camera_db_id)
        pipeline.start()
        self._pipelines[camera_db_id] = pipeline
        logger.info("PipelineManager: attached pipeline for camera %d", camera_db_id)
        return pipeline

    def detach(self, camera_db_id: int):
        """Stop and remove pipeline for given camera."""
        pipeline = self._pipelines.pop(camera_db_id, None)
        if pipeline:
            pipeline.stop()
            logger.info("PipelineManager: detached pipeline for camera %d", camera_db_id)

    def detach_all(self):
        for cam_id in list(self._pipelines.keys()):
            self.detach(cam_id)

    def get(self, camera_db_id: int) -> Optional[DetectionPipeline]:
        return self._pipelines.get(camera_db_id)

    def running_ids(self) -> list[int]:
        return list(self._pipelines.keys())


# ── Process-level singleton ─────────────────────────────────────────────────
_pipeline_manager: Optional[PipelineManager] = None


def get_pipeline_manager() -> PipelineManager:
    global _pipeline_manager
    if _pipeline_manager is None:
        _pipeline_manager = PipelineManager()
    return _pipeline_manager
