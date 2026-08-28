"""Anonymous, camera-local centroid tracker.

Adapted from the project's original modules/centroid_tracker.py: pure
geometric nearest-centroid matching (scipy cdist), no biometric or
identity signal of any kind. Track ids are per-camera-instance only —
a new CentroidTracker is created per camera and reset whenever that
camera's worker restarts, so ids never carry meaning across cameras.
"""
from collections import OrderedDict

import numpy as np
from scipy.spatial import distance as dist


class CentroidTracker:
    def __init__(self, max_disappeared: int = 15, max_distance: float = 0.15):
        # max_distance is in normalized (0-1) coordinate space, not pixels.
        self.next_object_id = 0
        self.objects: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self.bboxes: "OrderedDict[int, list[float]]" = OrderedDict()
        self.disappeared: "OrderedDict[int, int]" = OrderedDict()
        self.first_seen_wall_time: "OrderedDict[int, float]" = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def register(self, centroid, bbox, wall_time: float):
        oid = self.next_object_id
        self.objects[oid] = centroid
        self.bboxes[oid] = bbox
        self.disappeared[oid] = 0
        self.first_seen_wall_time[oid] = wall_time
        self.next_object_id += 1
        return oid

    def deregister(self, object_id: int):
        self.objects.pop(object_id, None)
        self.bboxes.pop(object_id, None)
        self.disappeared.pop(object_id, None)
        self.first_seen_wall_time.pop(object_id, None)

    def update(self, detections: list[list[float]], wall_time: float) -> dict[int, dict]:
        """detections: list of normalized [x1,y1,x2,y2]. Returns {track_id: {bbox, centroid}}."""
        if len(detections) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self._current()

        input_centroids = np.array([[(x1 + x2) / 2.0, (y1 + y2) / 2.0] for x1, y1, x2, y2 in detections])

        if len(self.objects) == 0:
            for i, bbox in enumerate(detections):
                self.register(input_centroids[i], bbox, wall_time)
            return self._current()

        object_ids = list(self.objects.keys())
        object_centroids = np.array(list(self.objects.values()))
        D = dist.cdist(object_centroids, input_centroids)

        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows, used_cols = set(), set()
        for row, col in zip(rows, cols):
            if row in used_rows or col in used_cols or D[row, col] > self.max_distance:
                continue
            object_id = object_ids[row]
            self.objects[object_id] = input_centroids[col]
            self.bboxes[object_id] = detections[col]
            self.disappeared[object_id] = 0
            used_rows.add(row)
            used_cols.add(col)

        unused_rows = set(range(D.shape[0])) - used_rows
        unused_cols = set(range(D.shape[1])) - used_cols

        for row in unused_rows:
            object_id = object_ids[row]
            self.disappeared[object_id] += 1
            if self.disappeared[object_id] > self.max_disappeared:
                self.deregister(object_id)

        for col in unused_cols:
            self.register(input_centroids[col], detections[col], wall_time)

        return self._current()

    def _current(self) -> dict[int, dict]:
        return {
            oid: {"bbox": self.bboxes[oid], "centroid": self.objects[oid].tolist(), "first_seen": self.first_seen_wall_time[oid]}
            for oid in self.objects
        }
