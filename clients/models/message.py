from dataclasses import dataclass

@dataclass
class Message:
    peer_type: str     # 'user' hoặc 'room'
    peer_id: str
    direction: str     # 'in' hoặc 'out'
    msg_type: str      # 'text' hoặc 'image'
    content: str
    ts: int