import time

class TypingTimer:
    def __init__(self, callback, idle_ms: int = 1500):
        self.callback = callback
        self.idle_ms = idle_ms
        self._last = 0.0
        self._typing = False

    def user_pressed(self):
        now = time.time()*1000
        if not self._typing:
            self._typing = True
            self.callback(True)
        self._last = now

    def tick(self):
        if self._typing and (time.time()*1000 - self._last) > self.idle_ms:
            self._typing = False
            self.callback(False)