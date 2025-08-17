# clients/notification/notifier.py
from datetime import datetime

def _ts():
    # timestamp ngắn gọn
    return datetime.now().strftime("%H:%M:%S")

def notify_new_private_message(sender: str, preview: str):
    print(f"[{_ts()}] [THÔNG BÁO] Tin nhắn mới từ {sender}: {preview}")

def notify_new_group_message(group: str, sender: str, preview: str):
    print(f"[{_ts()}] [THÔNG BÁO] Tin nhắn mới trong nhóm '{group}' từ {sender}: {preview}")

def notify_user_online(username: str):
    print(f"[{_ts()}] [TRẠNG THÁI] {username} vừa ONLINE")

def notify_user_offline(username: str):
    print(f"[{_ts()}] [TRẠNG THÁI] {username} vừa OFFLINE")

def notify_typing(username: str, context: str):
    # context: "private:<peer>" hoặc "group:<group_name>"
    print(f"[{_ts()}] [ĐANG GÕ] {username} đang gõ... ({context})")

def notify_read_receipt(context: str, message_id: str, by_user: str | None = None):
    # context: "private:<peer>" hoặc "group:<group_name>"
    # by_user có thể None trong chat 1-1
    if by_user:
        print(f"[{_ts()}] [ĐÃ ĐỌC] {by_user} đã đọc tin nhắn {message_id} ({context})")
    else:
        print(f"[{_ts()}] [ĐÃ ĐỌC] Tin nhắn {message_id} đã được đọc ({context})")
