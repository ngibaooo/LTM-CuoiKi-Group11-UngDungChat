from typing import Optional
from utils.events import EventBus

class AuthService:
    def __init__(self, send, bus: EventBus):
        self.send = send
        self.bus = bus
        self.token: Optional[str] = None
        self.username: Optional[str] = None

    def on_server(self, msg: dict):
        t = msg.get("type")
        if t == "auth.ok":
            self.token = msg.get("token")
            self.username = msg.get("username")
            self.bus.publish("auth/ok", {"username": self.username})
        elif t == "auth.error":
            self.bus.publish("auth/error", {"error": msg.get("error")})

    def register(self, username: str, password: str):
        self.send({"type": "auth.register", "username": username, "password": password})

    def login(self, username: str, password: str):
        self.send({"type": "auth.login", "username": username, "password": password})