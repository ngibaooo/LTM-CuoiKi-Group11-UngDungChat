# clients/friend/list.py
import json
from config import ENCODING, BUFFER_SIZE

def view_friend_list(sock):
    request = {
        'action': 'friend_list'
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Danh sách bạn bè:")
        for friend in data.get('friends', []):
            print(f" - {friend['username']} ({'Online' if friend['online'] else 'Offline'})")
    else:
        print("NO", data.get('message', 'Không thể lấy danh sách bạn bè.'))
