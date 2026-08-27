import numpy as np
from scipy.spatial import distance as dist
from collections import OrderedDict, defaultdict, deque
from datetime import datetime

class CentroidTracker:
    """Enhanced centroid tracker with accurate person tracking"""
    
    def __init__(self, max_disappeared=50, max_distance=120):
        self.next_object_id = 0
        self.objects = OrderedDict()
        self.disappeared = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.object_bboxes = OrderedDict()  # Store bounding boxes
        self.object_positions_history = defaultdict(lambda: deque(maxlen=20))
        self.last_seen = OrderedDict()
        
    def register(self, centroid, bbox):
        """Register new object with centroid and bounding box"""
        self.objects[self.next_object_id] = centroid
        self.object_bboxes[self.next_object_id] = bbox
        self.disappeared[self.next_object_id] = 0
        self.last_seen[self.next_object_id] = datetime.now()
        self.object_positions_history[self.next_object_id].append(centroid)
        self.next_object_id += 1
        
    def deregister(self, object_id):
        """Remove object from tracking"""
        if object_id in self.objects:
            del self.objects[object_id]
        if object_id in self.object_bboxes:
            del self.object_bboxes[object_id]
        if object_id in self.disappeared:
            del self.disappeared[object_id]
        if object_id in self.last_seen:
            del self.last_seen[object_id]  
        if object_id in self.object_positions_history:
            del self.object_positions_history[object_id]
            
    def update(self, detections_data):
        """Update tracker with detection data (list of [x1, y1, x2, y2])"""
        if len(detections_data) == 0:
            # Mark all objects as disappeared
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.get_objects_with_info()
            
        # Convert detections to centroids
        input_centroids = []
        input_bboxes = []
        
        for detection in detections_data:
            x1, y1, x2, y2 = detection
            cx = int((x1 + x2) / 2.0)
            cy = int((y1 + y2) / 2.0)
            input_centroids.append([cx, cy])
            input_bboxes.append([x1, y1, x2, y2])
            
        input_centroids = np.array(input_centroids)
        
        if len(self.objects) == 0:
            # Register all detections as new objects
            for i in range(len(input_centroids)):
                self.register(input_centroids[i], input_bboxes[i])
        else:
            # Match existing objects with new detections
            object_centroids = np.array(list(self.objects.values()))
            D = dist.cdist(object_centroids, input_centroids)
            
            # Find minimum distance matches
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]
            
            used_row_indexes = set()
            used_col_indexes = set()
            
            # Update matched objects
            for (row, col) in zip(rows, cols):
                if row in used_row_indexes or col in used_col_indexes:
                    continue
                    
                if D[row, col] > self.max_distance:
                    continue
                    
                object_id = list(self.objects.keys())[row]
                self.objects[object_id] = input_centroids[col]
                self.object_bboxes[object_id] = input_bboxes[col]
                self.disappeared[object_id] = 0
                self.last_seen[object_id] = datetime.now()
                self.object_positions_history[object_id].append(input_centroids[col])
                
                used_row_indexes.add(row)
                used_col_indexes.add(col)
                
            # Handle unmatched objects and detections
            unused_row_indexes = set(range(0, D.shape[0])).difference(used_row_indexes)
            unused_col_indexes = set(range(0, D.shape[1])).difference(used_col_indexes)
            
            # Mark unmatched objects as disappeared
            if D.shape[0] >= D.shape[1]:
                for row in unused_row_indexes:
                    object_id = list(self.objects.keys())[row]
                    self.disappeared[object_id] += 1
                    if self.disappeared[object_id] > self.max_disappeared:
                        self.deregister(object_id)
            else:
                # Register new objects for unmatched detections
                for col in unused_col_indexes:
                    self.register(input_centroids[col], input_bboxes[col])
                    
        return self.get_objects_with_info()
    
    def get_objects_with_info(self):
        """Return objects with additional tracking information (JSON serializable)"""
        objects_info = {}
        for object_id, centroid in self.objects.items():
            # Convert numpy arrays to lists for JSON serialization
            positions_history = [pos.tolist() if hasattr(pos, 'tolist') else list(pos) 
                               for pos in self.object_positions_history[object_id]]
            
            objects_info[str(object_id)] = {  # Convert key to string
                'centroid': centroid.tolist() if hasattr(centroid, 'tolist') else list(centroid),
                'bbox': self.object_bboxes[object_id],
                'last_seen': self.last_seen[object_id].isoformat(),
                'positions_history': positions_history,
                'is_stationary': self.is_object_stationary(object_id),
                'id': object_id
            }
        return objects_info
    
    def is_object_stationary(self, object_id, threshold=30):
        """Check if object has been stationary"""
        if object_id not in self.object_positions_history:
            return False
        positions = list(self.object_positions_history[object_id])
        if len(positions) < 8:
            return False
        
        # Calculate movement variance
        positions = np.array(positions)
        variance = np.var(positions, axis=0)
        return np.all(variance < threshold)
