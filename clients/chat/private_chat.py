import json
import threading
import os
from config import ENCODING, BUFFER_SIZE
from notification.notifier import (
    notify_new_private_message,
    notify_user_online, notify_user_offline,
    notify_typing, notify_read_receipt
)

def listen_for_messages(sock):
    os.makedirs("downloads", exist_ok=True)

    while True:
        try:
            message = sock.recv(BUFFER_SIZE).decode(ENCODING)
            if not message:
                break

            # Gói đầu vào JSON
            if message.startswith("{"):
                data = json.loads(message)
                action = data.get('action')

                # --- Tin nhắn 1-1 ---
                if action == 'private_message':
                    sender = data.get('from')
                    msg = data.get('message', '')
                    print(f"\n[{sender}]: {msg}")
                    # Thông báo ngắn (preview 50 ký tự)
                    notify_new_private_message(sender, msg[:50])

                # --- Nhận file ảnh 1-1 ---
                elif action == 'incoming_image':
                    filename = data['filename']
                    filesize = int(data['filesize'])
                    sender = data['from']
                    print(f"\n{sender} đã gửi một ảnh: {filename} ({filesize} bytes)")

                    with open(os.path.join("downloads", filename), "wb") as f:
                        received = 0
                        while received < filesize:
                            chunk = sock.recv(min(BUFFER_SIZE, filesize - received))
                            if not chunk:
                                break
                            f.write(chunk)
                            received += len(chunk)
                    print(f"Ảnh đã lưu: downloads/{filename}")
                    notify_new_private_message(sender, f"[Ảnh] {filename}")

                # --- Thông báo trạng thái online/offline ---
                elif action == 'notify_online':
                    user = data.get('username')
                    if user:
                        notify_user_online(user)

                elif action == 'notify_offline':
                    user = data.get('username')
                    if user:
                        notify_user_offline(user)

                # --- Đang gõ ---
                elif action == 'typing':
                    # context ví dụ: "private:<peer>"
                    user = data.get('username')
                    context = data.get('context', 'private')
                    if user:
                        notify_typing(user, context)

                # --- Đã đọc ---
                elif action == 'read_receipt':
                    # context: "private:<peer>"
                    context = data.get('context', 'private')
                    message_id = data.get('message_id', '?')
                    by_user = data.get('by_user')
                    notify_read_receipt(context, message_id, by_user)

                # --- Tin nhắn nhóm cũng có thể đẩy về chung socket; bỏ qua ở listener 1-1 ---
                # Các action nhóm sẽ được bắt ở group listener (nếu bạn dùng riêng).
                # Nếu muốn gộp một listener duy nhất cho cả app, bạn có thể xử lý thêm tại đây.

        except:
            break

def private_chat(sock):
    recipient = input("Nhập username người muốn trò chuyện: ")

    # Gửi yêu cầu bắt đầu cuộc trò chuyện
    request = {
        'action': 'start_private_chat',
        'to': recipient
    }
    sock.send(json.dumps(request).encode(ENCODING))

    # Tạo luồng lắng nghe tin nhắn
    listener = threading.Thread(target=listen_for_messages, args=(sock,))
    listener.daemon = True
    listener.start()

    print("Bắt đầu chat riêng (gõ /exit để thoát)...")
    while True:
        msg = input()
        if msg.lower() == "/exit":
            break

        message = {
            'action': 'send_private_message',
            'to': recipient,
            'message': msg
        }
        sock.send(json.dumps(message).encode(ENCODING))
