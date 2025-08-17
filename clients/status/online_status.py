# clients/status/online_status.py
import json
from config import ENCODING

VALID_STATES = {"online", "offline", "away"}

def set_status(sock, state: str):
    state = state.lower().strip()
    if state not in VALID_STATES:
        print("Trạng thái không hợp lệ. Hợp lệ: online/offline/away")
        return

    payload = {
        "action": "set_status",
        "state": state
    }
    sock.send(json.dumps(payload).encode(ENCODING))
    print(f"Đã gửi trạng thái: {state}")
