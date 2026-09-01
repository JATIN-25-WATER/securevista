import numpy as np
import cv2
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class ZoneAnalyzer:
    """Accurate zone-based analytics and heatmap generation"""
    
    def __init__(self, width, height, grid_size=(6, 6)):
        self.width = width
        self.height = height
        self.grid_size = grid_size
        self.zone_width = width // grid_size[0]
        self.zone_height = height // grid_size[1]
        self.heatmap = np.zeros(grid_size, dtype=np.float32)
        self.zone_counts = defaultdict(int)
        
    def update_zones(self, objects_info):
        """Update zone occupancy based on tracked objects"""
        current_zones = defaultdict(int)
        
        for object_id_str, info in objects_info.items():
            centroid = info['centroid']
            zone_x = min(int(centroid[0] // self.zone_width), self.grid_size[0] - 1)
            zone_y = min(int(centroid[1] // self.zone_height), self.grid_size[1] - 1)
            
            zone_x = max(0, zone_x)
            zone_y = max(0, zone_y)
            
            zone_key = f"{zone_x}_{zone_y}"  # Use string key for JSON serialization
            current_zones[zone_key] += 1
            self.zone_counts[zone_key] += 1
            self.heatmap[zone_y, zone_x] += 0.1  # Gradual heat accumulation
        
        return dict(current_zones)  # Convert to regular dict
    
    def get_heatmap_overlay(self, image):
        """Generate accurate heatmap overlay for visualization"""
        try:
            overlay = image.copy()
            
            # Normalize heatmap
            if np.max(self.heatmap) > 0:
                normalized_heatmap = (self.heatmap / np.max(self.heatmap) * 255).astype(np.uint8)
                colored_heatmap = cv2.applyColorMap(normalized_heatmap, cv2.COLORMAP_JET)
                resized_heatmap = cv2.resize(colored_heatmap, (self.width, self.height))
                
                # Blend with original image
                overlay = cv2.addWeighted(image, 0.6, resized_heatmap, 0.4, 0)
            
            # Draw grid lines
            for i in range(1, self.grid_size[0]):
                x = i * self.zone_width
                cv2.line(overlay, (x, 0), (x, self.height), (255, 255, 255), 1)
            
            for i in range(1, self.grid_size[1]):
                y = i * self.zone_height
                cv2.line(overlay, (0, y), (self.width, y), (255, 255, 255), 1)
                
            return overlay
        except Exception as e:
            logger.error(f"Error generating heatmap overlay: {e}")
            return image