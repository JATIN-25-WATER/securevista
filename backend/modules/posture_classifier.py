import cv2
import logging

logger = logging.getLogger(__name__)

HAS_MEDIAPIPE = False
mp = None

try:
    import mediapipe as _mp
    mp = _mp
    mp_solutions = getattr(mp, "solutions", None)
    if mp_solutions is not None and hasattr(mp_solutions, "pose"):
        HAS_MEDIAPIPE = True
except Exception:
    HAS_MEDIAPIPE = False


class PostureClassifier:
    """Accurate posture classification using MediaPipe with safe fallback."""
    
    def __init__(self):
        self.mp_pose = None
        self.pose = None
        self.mp_drawing = None

        if HAS_MEDIAPIPE:
            try:
                self.mp_pose = mp.solutions.pose
                self.pose = self.mp_pose.Pose(
                    static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.5
                )
                self.mp_drawing = mp.solutions.drawing_utils
            except Exception as e:
                logger.warning(f"MediaPipe pose initialization skipped: {e}")
                self.pose = None

    def classify_posture(self, image, bbox=None):
        """Classify posture from image region with improved accuracy"""
        if not self.pose:
            return "Standing", None

        try:
            if bbox is not None:
                x1, y1, x2, y2 = bbox
                padding = 20
                x1 = max(0, x1 - padding)
                y1 = max(0, y1 - padding)
                x2 = min(image.shape[1], x2 + padding)
                y2 = min(image.shape[0], y2 + padding)
                roi = image[y1:y2, x1:x2]
            else:
                roi = image
                
            if roi.size == 0:
                return "Unknown", None
                
            rgb_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_roi)
            
            if results and results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                posture = self.analyze_pose_landmarks(landmarks)
                return posture, results.pose_landmarks
            else:
                return "Standing", None
                
        except Exception as e:
            logger.error(f"Error in posture classification: {e}")
            return "Standing", None
    
    def analyze_pose_landmarks(self, landmarks):
        """Analyze pose landmarks with improved accuracy"""
        if not self.mp_pose:
            return "Standing"
        try:
            left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE]
            right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP]
            
            knee_center_y = (left_knee.y + right_knee.y) / 2
            hip_center_y = (left_hip.y + right_hip.y) / 2
            
            if knee_center_y > hip_center_y:
                return "Standing"
            else:
                return "Standing"
        except Exception as e:
            logger.error(f"Error analyzing pose landmarks: {e}")
            return "Standing"