from utils.events import EventBus

class PresenceService:
    def __init__(self, send, bus: EventBus):
        self.send = send
        self.bus = bus

    def on_server(self, msg: dict):
        t = msg.get("type")
        if t == "presence.update":
            self.bus.publish("presence/update", msg)

    def subscribe(self):
        self.send({"type": "presence.subscribe"})