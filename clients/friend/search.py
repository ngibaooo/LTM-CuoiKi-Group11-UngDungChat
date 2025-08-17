# clients/friend/search.py
import json
from config import ENCODING, BUFFER_SIZE

def search_user(sock):
    keyword = input("🔍 Tìm username: ")
    request = {
        'action': 'search_user',
        'keyword': keyword
    }
    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Kết quả tìm kiếm:")
        for user in data.get('users', []):
            print(f" - {user}")
    else:
        print("", data.get('message', 'Không tìm thấy người dùng nào.'))
