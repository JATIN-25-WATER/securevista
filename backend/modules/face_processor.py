import cv2
import logging

logger = logging.getLogger(__name__)

class FaceProcessor:
    """Face detection and blurring for privacy"""
    
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
    def process_faces(self, image, blur_faces=True):
        """Process faces in image - blur for privacy"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(30, 30))
            
            face_info = []
            processed_image = image.copy()
            
            for (x, y, w, h) in faces:
                if blur_faces:
                    face_roi = processed_image[y:y+h, x:x+w]
                    blurred_face = cv2.GaussianBlur(face_roi, (99, 99), 30)
                    processed_image[y:y+h, x:x+w] = blurred_face
                
                face_info.append({'bbox': [int(x), int(y), int(w), int(h)]})
                cv2.rectangle(processed_image, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
            return processed_image, face_info
        except Exception as e:
            logger.error(f"Error processing faces: {e}")
            return image, []

