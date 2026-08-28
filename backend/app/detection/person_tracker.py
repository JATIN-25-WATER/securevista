"""Person-only detection. This system deliberately detects a single object
class (COCO person) and does no face, biometric, or identity processing."""
import logging
import threading

from app.config import DETECTION_CONF_THRESHOLD, PERSON_CLASS_ID, YOLO_MODEL_PATH

logger = logging.getLogger("cctv.detection")

_model = None
_model_lock = threading.Lock()
_predict_lock = threading.Lock()  # ultralytics YOLO.predict() is not safe to call concurrently
# from multiple threads on the same model instance -- serialize inference across camera workers.
_device = None


def get_model():
    """Lazily loads a single shared YOLOv8n model instance (thread-safe),
    on CUDA if available, otherwise CPU."""
    global _model, _device
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            import torch
            from ultralytics import YOLO

            _device = "cuda" if torch.cuda.is_available() else "cpu"
            weights = str(YOLO_MODEL_PATH) if YOLO_MODEL_PATH.exists() else "yolov8n.pt"
            model = YOLO(weights)
            model.to(_device)
            logger.info("YOLOv8n person detector loaded on %s", _device)
            _model = model
    return _model


def get_device() -> str:
    get_model()
    return _device


def detect_persons(frame) -> list[dict]:
    """Runs person-only detection on a BGR frame. Returns a list of
    {bbox: [x1,y1,x2,y2] normalized 0-1, confidence: float}."""
    model = get_model()
    h, w = frame.shape[:2]
    with _predict_lock:
        results = model.predict(
            frame,
            classes=[PERSON_CLASS_ID],
            conf=DETECTION_CONF_THRESHOLD,
            verbose=False,
        )
    detections = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append({
                "bbox": [max(0.0, x1 / w), max(0.0, y1 / h), min(1.0, x2 / w), min(1.0, y2 / h)],
                "confidence": conf,
            })
    return detections
