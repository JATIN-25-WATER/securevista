import math
from collections import defaultdict

class LineCounter:
    """Enhanced line crossing counter for entry/exit tracking"""
    
    def __init__(self, line_start, line_end, buffer_zone=20, min_confidence_frames=3):
        self.line_start = line_start
        self.line_end = line_end
        self.buffer_zone = buffer_zone  # Pixels around line for detection zone
        self.min_confidence_frames = min_confidence_frames  # Minimum frames to confirm crossing
        
        # Track object states
        self.object_states = defaultdict(lambda: {
            'positions_history': [],
            'line_side_history': [],
            'crossing_state': 'none',  # none, approaching, crossing, crossed
            'crossing_direction': None,
            'confidence_count': 0,
            'last_seen_frame': 0
        })
        
        self.crossed_objects = set()
        self.entry_count = 0
        self.exit_count = 0
        self.frame_count = 0
        
        # Calculate line properties
        self._calculate_line_properties()
        
    def _calculate_line_properties(self):
        """Calculate line equation and normal vector"""
        self.line_vec = (
            self.line_end[0] - self.line_start[0],
            self.line_end[1] - self.line_start[1]
        )
        self.line_length = math.sqrt(self.line_vec[0]**2 + self.line_vec[1]**2)
        
        # Normalized line vector
        if self.line_length > 0:
            self.line_unit = (
                self.line_vec[0] / self.line_length,
                self.line_vec[1] / self.line_length
            )
            # Normal vector (perpendicular to line, pointing "right" of line direction)
            self.normal_vec = (-self.line_unit[1], self.line_unit[0])
        else:
            self.line_unit = (1, 0)
            self.normal_vec = (0, 1)
    
    def _point_to_line_distance(self, point):
        """Calculate signed distance from point to line"""
        x, y = point
        x1, y1 = self.line_start
        
        # Vector from line start to point
        to_point = (x - x1, y - y1)
        
        # Signed distance (positive on one side, negative on other)
        return (to_point[0] * self.normal_vec[0] + to_point[1] * self.normal_vec[1])
    
    def _get_line_side(self, point):
        """Get which side of line the point is on (-1, 0, or 1)"""
        distance = self._point_to_line_distance(point)
        if abs(distance) < 2:  # Very close to line
            return 0
        return 1 if distance > 0 else -1
    
    def _is_near_line(self, point):
        """Check if point is within buffer zone of the line"""
        return abs(self._point_to_line_distance(point)) <= self.buffer_zone
    
    def _detect_crossing_pattern(self, object_state):
        """Detect if object has crossed the line based on position history"""
        positions = object_state['positions_history']
        sides = object_state['line_side_history']
        
        if len(positions) < 2 or len(sides) < 2:
            return False, None
            
        # Look for clear side transition
        recent_sides = sides[-5:]  # Check last 5 positions
        
        # Remove zeros (on-line positions) for cleaner analysis
        non_zero_sides = [s for s in recent_sides if s != 0]
        
        if len(non_zero_sides) < 2:
            return False, None
            
        # Check for side change
        first_side = non_zero_sides[0]
        last_side = non_zero_sides[-1]
        
        if first_side != last_side:
            # Determine direction based on normal vector orientation
            # If normal points right of line direction:
            # -1 to 1: entry (crossing from left to right)
            # 1 to -1: exit (crossing from right to left)
            if first_side == -1 and last_side == 1:
                return True, 'entry'
            elif first_side == 1 and last_side == -1:
                return True, 'exit'
                
        return False, None
    
    def _line_segment_intersection(self, p1, p2):
        """Check if line segment p1-p2 intersects with counting line"""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = self.line_start
        x4, y4 = self.line_end
        
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(denom) < 1e-10:
            return False
            
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
        
        return 0 <= t <= 1 and 0 <= u <= 1
    
    def update(self, objects_info):
        """Update line crossing counts with enhanced detection"""
        self.frame_count += 1
        current_object_ids = set()
        
        for object_id_str, info in objects_info.items():
            object_id = int(object_id_str)
            current_object_ids.add(object_id)
            
            centroid = info['centroid']
            state = self.object_states[object_id]
            
            # Update position history (keep last 10 positions)
            state['positions_history'].append(centroid)
            if len(state['positions_history']) > 10:
                state['positions_history'].pop(0)
            
            # Update line side history
            line_side = self._get_line_side(centroid)
            state['line_side_history'].append(line_side)
            if len(state['line_side_history']) > 10:
                state['line_side_history'].pop(0)
            
            state['last_seen_frame'] = self.frame_count
            
            # Skip if not enough history
            if len(state['positions_history']) < 2:
                continue
            
            # Check for crossing using multiple methods
            crossed = False
            direction = None
            
            # Method 1: Line segment intersection
            prev_pos = state['positions_history'][-2]
            curr_pos = state['positions_history'][-1]
            
            if self._line_segment_intersection(prev_pos, curr_pos):
                # Determine direction based on side transition
                prev_side = self._get_line_side(prev_pos)
                curr_side = self._get_line_side(curr_pos)
                
                if prev_side != curr_side and prev_side != 0 and curr_side != 0:
                    if prev_side == -1 and curr_side == 1:
                        direction = 'entry'
                    elif prev_side == 1 and curr_side == -1:
                        direction = 'exit'
                    crossed = True
            
            # Method 2: Pattern-based detection for missed intersections
            if not crossed:
                crossed, direction = self._detect_crossing_pattern(state)
            
            # Method 3: Confidence-based detection for objects near line
            if not crossed and self._is_near_line(centroid):
                if state['crossing_state'] == 'none':
                    state['crossing_state'] = 'approaching'
                elif state['crossing_state'] == 'approaching':
                    # Check if we have a clear direction
                    _, potential_direction = self._detect_crossing_pattern(state)
                    if potential_direction:
                        state['confidence_count'] += 1
                        state['crossing_direction'] = potential_direction
                        
                        if state['confidence_count'] >= self.min_confidence_frames:
                            crossed = True
                            direction = potential_direction
                            state['crossing_state'] = 'crossed'
            else:
                # Reset approaching state if moved away from line
                if not self._is_near_line(centroid):
                    state['crossing_state'] = 'none'
                    state['confidence_count'] = 0
                    state['crossing_direction'] = None
            
            # Record crossing if detected and not already counted
            if crossed and direction and object_id not in self.crossed_objects:
                self.crossed_objects.add(object_id)
                
                if direction == 'entry':
                    self.entry_count += 1
                    print(f"ENTRY detected for object {object_id} at frame {self.frame_count}")
                elif direction == 'exit':
                    self.exit_count += 1
                    print(f"EXIT detected for object {object_id} at frame {self.frame_count}")
                
                # Reset state after counting
                state['crossing_state'] = 'crossed'
                state['confidence_count'] = 0
        
        # Clean up old objects that haven't been seen recently
        self._cleanup_old_objects(current_object_ids)
    
    def _cleanup_old_objects(self, current_object_ids, max_frames_absent=30):
        """Remove tracking data for objects not seen recently"""
        objects_to_remove = []
        
        for object_id, state in self.object_states.items():
            if (object_id not in current_object_ids and 
                self.frame_count - state['last_seen_frame'] > max_frames_absent):
                objects_to_remove.append(object_id)
        
        for object_id in objects_to_remove:
            del self.object_states[object_id]
            self.crossed_objects.discard(object_id)
    
    def reset_counts(self):
        """Reset all counts and tracked objects"""
        self.crossed_objects.clear()
        self.entry_count = 0
        self.exit_count = 0
        self.object_states.clear()
        self.frame_count = 0
    
    def get_counts(self):
        """Get current entry and exit counts"""
        return {
            'entries': self.entry_count,
            'exits': self.exit_count,
            'net': self.entry_count - self.exit_count
        }
    
    def set_line(self, line_start, line_end):
        """Update the counting line position"""
        self.line_start = line_start
        self.line_end = line_end
        self._calculate_line_properties()
        # Reset tracking when line changes
        self.reset_counts()

# Usage example:
"""
# Initialize line counter
line_start = (100, 200)  # Start point of counting line
line_end = (400, 200)    # End point of counting line
counter = LineCounter(line_start, line_end, buffer_zone=25, min_confidence_frames=2)

# In your tracking loop:
objects_info = {
    "1": {
        "centroid": (250, 180),
        "positions_history": [...] # This parameter is now handled internally
    }
}

counter.update(objects_info)
counts = counter.get_counts()
print(f"Entries: {counts['entries']}, Exits: {counts['exits']}, Net: {counts['net']}")
"""