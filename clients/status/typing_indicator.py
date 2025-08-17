# clients/status/typing_indicator.py
import json
import time
from config import ENCODING

def typing_private(sock, peer_username: str):
    """
    Gửi ping 'đang gõ' trong ngữ cảnh chat 1-1 tới server.
    Dùng khi người dùng đang nhập liệu cho hội thoại với peer_username.
    """
    payload = {
        "action": "typing_ping",
        "context": "private",
        "peer": peer_username
    }
    sock.send(json.dumps(payload).encode(ENCODING))

def typing_group(sock, group_name: str):
    """
    Gửi ping 'đang gõ' trong ngữ cảnh chat nhóm.
    """
    payload = {
        "action": "typing_ping",
        "context": "group",
        "group": group_name
    }
    sock.send(json.dumps(payload).encode(ENCODING))

def typing_burst(sock, context: str, target: str, duration_sec: float = 2.0, interval_sec: float = 0.8):
    """
    Gửi nhiều ping 'đang gõ' trong khoảng duration_sec để server duy trì trạng thái 'typing'.
    context: "private" -> target = peer_username ; "group" -> target = group_name
    """
    end_ts = time.time() + duration_sec
    while time.time() < end_ts:
        if context == "private":
            typing_private(sock, target)
        elif context == "group":
            typing_group(sock, target)
        time.sleep(interval_sec)
