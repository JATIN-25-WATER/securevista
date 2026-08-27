import cv2
import numpy as np
from ultralytics import YOLO
import supervision as sv
import torch
import threading
import time
from datetime import datetime
import logging

from .centroid_tracker import CentroidTracker
from .line_counter import LineCounter
from .posture_classifier import PostureClassifier
from .face_processor import FaceProcessor
from .zone_analyzer import ZoneAnalyzer

logger = logging.getLogger(__name__)


class Enhanced2A2SDetector:
    """Main enhanced surveillance system with accurate detection."""

    def __init__(self, cap):
        self.cap = cap

        self.yolo_model = None
        self.tracker = CentroidTracker(max_disappeared=50, max_distance=120)
        self.posture_classifier = PostureClassifier()
        self.face_processor = FaceProcessor()

        self.running = False
        self.detection_thread = None
        self._frame_lock = threading.Lock()

        self.export_frame = None
        self.frame_width = 1280
        self.frame_height = 720

        self.zone_analyzer = ZoneAnalyzer(self.frame_width, self.frame_height)

        line_y = self.frame_height // 2
        self.line_counter = LineCounter((100, line_y), (self.frame_width - 100, line_y))

        self.inactivity_threshold = 120
        self.blur_faces = True
        self.show_poses = True
        self.show_zones = False
        self.show_line_counter = True

        self.stats = {
            "total_detections": 0,
            "current_people_count": 0,
            "entry_count": 0,
            "exit_count": 0,
            "inactivity_alerts": 0,
        }

        self.initialize_models()

    def initialize_models(self):
        try:
            self.yolo_model = YOLO("yolov8n.pt")
            if torch.cuda.is_available():
                self.yolo_model.to("cuda")
            logger.info("YOLO model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading YOLO model: {e}")

    def start_detection(self):
        if not self.running:
            self.running = True
            self.detection_thread = threading.Thread(target=self.detection_loop)
            self.detection_thread.daemon = True
            self.detection_thread.start()
            logger.info("Enhanced 2A2S Detection started")

    def stop_detection(self):
        self.running = False
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
        logger.info("Detection stopped")

    def detection_loop(self):
        consecutive_errors = 0
        max_consecutive_errors = 10

        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    logger.info("End of video reached, rewinding...")
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                consecutive_errors = 0
                frame = cv2.resize(frame, (self.frame_width, self.frame_height))
                processed_frame = self.process_frame(frame)

                with self._frame_lock:
                    self.export_frame = processed_frame.copy()

                time.sleep(0.033)

            except Exception as e:
                logger.error(f"Error in detection loop: {e}")
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    break
                error_frame = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
                cv2.putText(
                    error_frame,
                    f"Detection Error: {str(e)[:50]}",
                    (50, self.frame_height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    2,
                )
                with self._frame_lock:
                    self.export_frame = error_frame
                time.sleep(1)

    def process_frame(self, frame):
        timestamp = datetime.now()
        person_boxes = []

        if self.yolo_model:
            try:
                results = self.yolo_model(frame, verbose=False)[0]
                detections = sv.Detections.from_ultralytics(results)
                person_mask = (detections.class_id == 0) & (detections.confidence > 0.5)
                person_detections = detections[person_mask]
                person_boxes = person_detections.xyxy.astype(int).tolist()
                self.stats["total_detections"] = len(person_boxes)
            except Exception as e:
                logger.error(f"Error in person detection: {e}")

        objects_info = self.tracker.update(person_boxes)
        self.stats["current_people_count"] = len(objects_info)

        if self.blur_faces:
            frame, _face_info = self.face_processor.process_faces(frame, blur_faces=True)

        for obj_id_str, info in objects_info.items():
            try:
                obj_id = int(obj_id_str)
                centroid = info["centroid"]
                bbox = info["bbox"]
                x1, y1, x2, y2 = bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(frame, (int(centroid[0]), int(centroid[1])), 5, (0, 255, 0), -1)

                if self.show_poses:
                    posture, _pose_landmarks = self.posture_classifier.classify_posture(frame, bbox)
                    cv2.putText(
                        frame,
                        posture,
                        (x1, y2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 255),
                        2,
                    )

                if info["is_stationary"]:
                    last_seen = datetime.fromisoformat(info["last_seen"])
                    time_stationary = (timestamp - last_seen).total_seconds()
                    if time_stationary > self.inactivity_threshold:
                        cv2.putText(
                            frame,
                            "INACTIVE!",
                            (int(centroid[0]) - 30, int(centroid[1]) + 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 165, 255),
                            2,
                        )
                        self.stats["inactivity_alerts"] += 1
                        logger.info(
                            "Inactivity alert: object %s stationary %.0fs",
                            obj_id,
                            time_stationary,
                        )
            except Exception as e:
                logger.error(f"Error processing object {obj_id_str}: {e}")
                continue

        self.line_counter.update(objects_info)
        self.stats["entry_count"] = self.line_counter.entry_count
        self.stats["exit_count"] = self.line_counter.exit_count

        if self.show_line_counter:
            cv2.line(frame, self.line_counter.line_start, self.line_counter.line_end, (255, 255, 0), 3)

        current_zones = self.zone_analyzer.update_zones(objects_info)
        if self.show_zones:
            frame = self.zone_analyzer.get_heatmap_overlay(frame)

        self.add_info_overlay(frame, timestamp)
        return frame

    def add_info_overlay(self, frame, timestamp):
        try:
            overlay = frame.copy()
            cv2.rectangle(overlay, (10, frame.shape[0] - 220), (450, frame.shape[0] - 10), (0, 0, 0), -1)
            frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
            y_offset = frame.shape[0] - 200
            cv2.putText(
                frame,
                f"Current People: {self.stats['current_people_count']}",
                (15, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                frame,
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                (frame.shape[1] - 250, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
        except Exception as e:
            logger.error(f"Error adding info overlay: {e}")

    def get_export_frame(self):
        with self._frame_lock:
            return self.export_frame.copy() if self.export_frame is not None else None

    def cleanup(self):
        self.stop_detection()
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
