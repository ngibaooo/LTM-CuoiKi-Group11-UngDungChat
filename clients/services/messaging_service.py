import time
from utils.events import EventBus
from .storage import Storage

class MessagingService:
    def __init__(self, send, bus: EventBus, storage: Storage):
        self.send = send
        self.bus = bus
        self.storage = storage

    def on_server(self, msg: dict):
        t = msg.get("type")
        if t == "message" or t == "message.image":
            # Lưu local để search
            peer_type = msg.get("peer_type")  # 'user' hoặc 'room'
            peer_id = msg.get("peer_id")
            msg_type = "image" if t == "message.image" else "text"
            content = msg.get("content")
            ts = int(msg.get("ts", time.time()*1000))
            self.storage.save_message(peer_type, peer_id, "in", msg_type, content, ts)
            self.bus.publish("chat/message", msg)
        elif t == "typing":
            self.bus.publish("chat/typing", msg)

    # API
    def send_text_to_user(self, username: str, content: str):
        ts = int(time.time()*1000)
        self.storage.save_message("user", username, "out", "text", content, ts)
        self.send({"type": "message.send", "to_user": username, "content": content})

    def send_text_to_room(self, room_id: str, content: str):
        ts = int(time.time()*1000)
        self.storage.save_message("room", room_id, "out", "text", content, ts)
        self.send({"type": "message.send", "room_id": room_id, "content": content})

    def send_image_to_user(self, username: str, b64: str):
        ts = int(time.time()*1000)
        self.storage.save_message("user", username, "out", "image", b64, ts)
        self.send({"type": "message.image", "to_user": username, "b64": b64})

    def send_image_to_room(self, room_id: str, b64: str):
        ts = int(time.time()*1000)
        self.storage.save_message("room", room_id, "out", "image", b64, ts)
        self.send({"type": "message.image", "room_id": room_id, "b64": b64})

    def typing_to_user(self, username: str, is_typing: bool):
        self.send({"type": "typing", "to_user": username, "typing": is_typing})

    def typing_to_room(self, room_id: str, is_typing: bool):
        self.send({"type": "typing", "room_id": room_id, "typing": is_typing})