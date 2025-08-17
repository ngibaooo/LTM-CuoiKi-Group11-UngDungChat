# clients/friend/add_remove.py
import json
from config import ENCODING, BUFFER_SIZE

def send_friend_request(sock):
    to_user = input(" Gửi lời mời kết bạn đến (username): ")
    request = {
        'action': 'friend_request',
        'to_user': to_user
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Đã gửi lời mời kết bạn.")
    else:
        print("", data.get('message', 'Không gửi được lời mời.'))

def remove_friend(sock):
    to_user = input(" Nhập username muốn xóa khỏi bạn bè: ")
    request = {
        'action': 'remove_friend',
        'to_user': to_user
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Đã xóa bạn thành công.")
    else:
        print("", data.get('message', 'Không thể xóa bạn.'))

def respond_to_request(sock):
    from_user = input("👤 Username người gửi lời mời: ")
    response_action = input("Chấp nhận (a) / Từ chối (r): ").lower()
    if response_action not in ['a', 'r']:
        print(" Lựa chọn không hợp lệ.")
        return

    request = {
        'action': 'respond_friend_request',
        'from_user': from_user,
        'response': 'accept' if response_action == 'a' else 'reject'
    }

    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print("Đã xử lý lời mời kết bạn.")
    else:
        print("", data.get('message', 'Không thể xử lý lời mời.'))
