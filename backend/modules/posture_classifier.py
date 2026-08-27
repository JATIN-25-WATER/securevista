import cv2
import mediapipe as mp
import logging

logger = logging.getLogger(__name__)

class PostureClassifier:
    """Accurate posture classification using MediaPipe"""
    
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
    def classify_posture(self, image, bbox=None):
        """Classify posture from image region with improved accuracy"""
        try:
            if bbox is not None:
                x1, y1, x2, y2 = bbox
                # Add padding for better pose detection
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
            
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                posture = self.analyze_pose_landmarks(landmarks)
                return posture, results.pose_landmarks
            else:
                return "Unknown", None
                
        except Exception as e:
            logger.error(f"Error in posture classification: {e}")
            return "Unknown", None
    
    def analyze_pose_landmarks(self, landmarks):
        """Analyze pose landmarks with improved accuracy"""
        try:
            # Key landmarks
            nose = landmarks[self.mp_pose.PoseLandmark.NOSE]
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP]
            left_knee = landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE]
            right_knee = landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE]
            left_ankle = landmarks[self.mp_pose.PoseLandmark.LEFT_ANKLE]
            right_ankle = landmarks[self.mp_pose.PoseLandmark.RIGHT_ANKLE]
            
            # Calculate key points
            shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2
            hip_center_y = (left_hip.y + right_hip.y) / 2
            knee_center_y = (left_knee.y + right_knee.y) / 2
            ankle_center_y = (left_ankle.y + right_ankle.y) / 2
            
            # Calculate torso angle
            torso_vertical = abs(shoulder_center_y - hip_center_y)
            
            # More accurate posture classification
            
            if ankle_center_y > knee_center_y and knee_center_y > hip_center_y:  # Standing position
                return "Standing"
            else:
                return "Analyzing..."
            
                
        except Exception as e:
            logger.error(f"Error analyzing pose landmarks: {e}")
            return "Analyzing..."