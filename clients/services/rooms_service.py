from utils.events import EventBus

class RoomsService:
    def __init__(self, send, bus: EventBus):
        self.send = send
        self.bus = bus

    def on_server(self, msg: dict):
        t = msg.get("type")
        if t == "rooms.list":
            self.bus.publish("rooms/list", msg)
        elif t == "rooms.update":
            self.bus.publish("rooms/update", msg)

    # API
    def list(self):
        self.send({"type": "rooms.list"})

    def create(self, name: str):
        self.send({"type": "rooms.create", "name": name})

    def join(self, room_id: str):
        self.send({"type": "rooms.join", "room_id": room_id})

    def leave(self, room_id: str):
        self.send({"type": "rooms.leave", "room_id": room_id})