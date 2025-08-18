import queue
from typing import Callable, Dict, List

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._queue: "queue.Queue[tuple[str, dict]]" = queue.Queue()

    def publish(self, topic: str, payload: dict):
        self._queue.put((topic, payload))

    def subscribe(self, topic: str, handler: Callable[[dict], None]):
        self._subscribers.setdefault(topic, []).append(handler)

    def drain(self):
        """Được gọi từ UI thread (root.after) để xử lý an toàn."""
        while True:
            try:
                topic, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            for h in self._subscribers.get(topic, []):
                h(payload)