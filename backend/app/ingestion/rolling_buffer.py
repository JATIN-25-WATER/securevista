import threading
import time
from collections import deque


class RollingBuffer:
    """Thread-safe, time-bounded ring of (wall_time, frame) pairs used for
    pre-event evidence capture. Frames are stored as already-encoded JPEG
    bytes to keep memory bounded and avoid holding large numpy arrays."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._lock = threading.Lock()
        self._items: deque[tuple[float, bytes, list]] = deque()  # O(1) eviction from the left

    def add(self, jpeg_bytes: bytes, wall_time: float | None = None, bboxes: list | None = None):
        wall_time = wall_time if wall_time is not None else time.time()
        with self._lock:
            self._items.append((wall_time, jpeg_bytes, bboxes or []))
            cutoff = wall_time - self.seconds
            while self._items and self._items[0][0] < cutoff:
                self._items.popleft()

    def snapshot(self, seconds: float | None = None) -> list[tuple[float, bytes, list]]:
        with self._lock:
            if seconds is None:
                return list(self._items)
            cutoff = time.time() - seconds
            return [item for item in self._items if item[0] >= cutoff]
