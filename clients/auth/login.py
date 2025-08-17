# clients/auth/login.py
import json
from config import ENCODING, BUFFER_SIZE

def login(sock):
    username = input(" Username: ")
    password = input(" Password: ")

    request = {
        'action': 'login',
        'username': username,
        'password': password
    }

    sock.send(json.dumps(request).encode(ENCODING))
    response = sock.recv(BUFFER_SIZE).decode(ENCODING)
    data = json.loads(response)

    if data.get('status') == 'success':
        print(" Đăng nhập thành công.")
        return True
    else:
        print("NO", data.get('message', 'Đăng nhập thất bại.'))
        return False
