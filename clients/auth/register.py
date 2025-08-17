# clients/auth/register.py
import json
from config import ENCODING, BUFFER_SIZE

def register(sock):
    username = input(" Nhập username mới: ")
    password = input(" Nhập password: ")

    request = {
        'action': 'register',
        'username': username,
        'password': password
    }

    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Đăng ký thành công. Hãy đăng nhập.")
    else:
        print("NO", data.get('message', 'Đăng ký thất bại.'))
