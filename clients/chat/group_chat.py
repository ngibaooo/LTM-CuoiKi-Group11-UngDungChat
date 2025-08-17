# clients/chat/group_chat.py
import json
import threading
from config import ENCODING, BUFFER_SIZE
from notification.notifier import (
    notify_new_group_message,
    notify_user_online, notify_user_offline,
    notify_typing, notify_read_receipt
)

def listen_group_messages(sock):
    while True:
        try:
            message = sock.recv(BUFFER_SIZE).decode(ENCODING)
            if not message:
                break
            if message.startswith("{"):
                data = json.loads(message)
                action = data.get('action')

                if action == 'group_message':
                    sender = data.get('from')
                    group = data.get('group')
                    msg = data.get('message', '')
                    print(f"\n[{group}] {sender}: {msg}")
                    notify_new_group_message(group, sender, msg[:50])

                # Online/Offline (có thể gửi kèm group)
                elif action == 'notify_online':
                    user = data.get('username')
                    if user:
                        notify_user_online(user)

                elif action == 'notify_offline':
                    user = data.get('username')
                    if user:
                        notify_user_offline(user)

                # Đang gõ trong group
                elif action == 'typing':
                    user = data.get('username')
                    group = data.get('group') or data.get('context', 'group')
                    if user:
                        notify_typing(user, f"group:{group}")

                # Đã đọc trong group
                elif action == 'read_receipt':
                    message_id = data.get('message_id', '?')
                    by_user = data.get('by_user')
                    group = data.get('group') or 'group'
                    notify_read_receipt(f"group:{group}", message_id, by_user)

        except:
            break

def create_group(sock):
    group_name = input("Tên nhóm: ")
    request = {
        'action': 'create_group',
        'group_name': group_name
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    print(response)

def add_member(sock):
    group_name = input("Tên nhóm: ")
    username = input("Username muốn thêm: ")
    request = {
        'action': 'add_group_member',
        'group_name': group_name,
        'username': username
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    print(response)

def remove_member(sock):
    group_name = input("Tên nhóm: ")
    username = input("Username muốn xóa: ")
    request = {
        'action': 'remove_group_member',
        'group_name': group_name,
        'username': username
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    print(response)

def leave_group(sock):
    group_name = input("Tên nhóm muốn rời: ")
    request = {
        'action': 'leave_group',
        'group_name': group_name
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    print(response)

def chat_in_group(sock):
    group_name = input("Tên nhóm muốn chat: ")
    request = {
        'action': 'join_group_chat',
        'group_name': group_name
    }
    sock.send(json.dumps(request).encode(ENCODING))

    # Lắng nghe tin nhắn nhóm
    listener = threading.Thread(target=listen_group_messages, args=(sock,))
    listener.daemon = True
    listener.start()

    print("Bắt đầu chat nhóm (gõ /exit để thoát)...")
    while True:
        msg = input()
        if msg.lower() == "/exit":
            break
        message = {
            'action': 'send_group_message',
            'group_name': group_name,
            'message': msg
        }
        sock.send(json.dumps(message).encode(ENCODING))
