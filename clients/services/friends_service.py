from utils.events import EventBus

class FriendsService:
    def __init__(self, send, bus: EventBus):
        self.send = send
        self.bus = bus

    def on_server(self, msg: dict):
        t = msg.get("type")
        if t == "friends.list":
            self.bus.publish("friends/list", msg)
        elif t == "friends.update":  # thêm/xóa/accept
            self.bus.publish("friends/update", msg)
        elif t == "friends.search.result":
            self.bus.publish("friends/search", msg)

    # API
    def list(self):
        self.send({"type": "friends.list"})

    def search(self, keyword: str):
        self.send({"type": "friends.search", "q": keyword})

    def add(self, username: str):
        self.send({"type": "friends.add", "username": username})

    def accept(self, username: str):
        self.send({"type": "friends.accept", "username": username})

    def decline(self, username: str):
        self.send({"type": "friends.decline", "username": username})

    def remove(self, username: str):
        self.send({"type": "friends.remove", "username": username})