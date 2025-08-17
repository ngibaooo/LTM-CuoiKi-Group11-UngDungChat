# clients/status/read_receipt.py
import json
from config import ENCODING

def mark_read_private(sock, peer_username: str, message_id: str):
    """
    Xác nhận đã đọc một tin nhắn 1-1. message_id do server cấp trong gói tin đến.
    """
    payload = {
        "action": "mark_read",
        "context": "private",
        "peer": peer_username,
        "message_id": message_id
    }
    sock.send(json.dumps(payload).encode(ENCODING))

def mark_read_group(sock, group_name: str, message_id: str):
    """
    Xác nhận đã đọc một tin nhắn trong nhóm.
    """
    payload = {
        "action": "mark_read",
        "context": "group",
        "group": group_name,
        "message_id": message_id
    }
    sock.send(json.dumps(payload).encode(ENCODING))
