import socket
import threading
from database import get_connection
from hashlib import sha256
import json

# Hàm mã hóa mật khẩu
def hash_password(password):
    return sha256(password.encode()).hexdigest()

# Hàm xử lý kết nối của client
def handle_client(client_socket):
    while True:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                break
            request = json.loads(data)
            
            if request['action'] == 'register':
                register_user(request, client_socket)
            elif request['action'] == 'login':
                login_user(request, client_socket)
            elif request['action'] == 'send_message':
                send_message(request, client_socket)
            elif request['action'] == 'receive_message':
                receive_messages(request, client_socket)

        except Exception as e:
            print(f"Error handling client: {e}")
            break
    client_socket.close()

# Hàm đăng ký người dùng
def register_user(request, client_socket):
    username = request['username']
    password = hash_password(request['password'])
    email = request['email']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    if cursor.fetchone():
        client_socket.send("Username already exists.".encode())
        return
    
    cursor.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)", 
                   (username, password, email))
    conn.commit()
    client_socket.send("Registration successful.".encode())
    conn.close()

# Hàm đăng nhập người dùng
def login_user(request, client_socket):
    username = request['username']
    password = hash_password(request['password'])
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
    user = cursor.fetchone()
    
    if user:
        client_socket.send("Login successful.".encode())
    else:
        client_socket.send("Invalid username or password.".encode())
    conn.close()

# Hàm gửi tin nhắn
def send_message(request, client_socket):
    sender_id = request['sender_id']
    receiver_id = request['receiver_id']
    content = request['content']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (%s, %s, %s)", 
                   (sender_id, receiver_id, content))
    conn.commit()
    client_socket.send("Message sent.".encode())
    conn.close()

# Hàm nhận tin nhắn
def receive_messages(request, client_socket):
    user_id = request['user_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM messages WHERE receiver_id = %s", (user_id,))
    messages = cursor.fetchall()
    
    message_list = []
    for message in messages:
        message_list.append({
            'sender_id': message[1],
            'receiver_id': message[2],
            'content': message[3],
            'send_at': message[4]
        })
    
    client_socket.send(json.dumps(message_list).encode())
    conn.close()

# Hàm khởi tạo server
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 5000))  # Lắng nghe ở cổng 5000
    server.listen(5)
    print("Server started on port 5000...")
    
    while True:
        client_socket, client_address = server.accept()
        print(f"New connection from {client_address}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()

if __name__ == "__main__":
    start_server()
