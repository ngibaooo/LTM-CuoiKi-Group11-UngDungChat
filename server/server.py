import socket
import threading
from database import get_connection
from hashlib import sha256
import json

# Hàm mã hóa mật khẩu
def hash_password(password):
    return sha256(password.encode()).hexdigest()

# Hàm gửi tin nhắn tới tất cả các thành viên trong phòng chat
def broadcast_message(room_id, message, sender_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Lấy tất cả thành viên của phòng chat
    cursor.execute("SELECT user_id FROM room_members WHERE room_id = %s", (room_id,))
    members = cursor.fetchall()
    
    # Gửi tin nhắn tới tất cả các thành viên
    for member in members:
        if member[0] != sender_id:  # Không gửi cho người gửi
            user_socket = user_sockets.get(member[0])  # Lưu socket của user khi đăng nhập
            if user_socket:
                try:
                    user_socket.send(json.dumps({"action": "receive_message", "message": message}).encode())
                except:
                    pass
    conn.close()

# Hàm xử lý kết nối của client
def handle_client(client_socket):
    user_id = None
    try:
        while True:
            data = client_socket.recv(1024).decode()
            if not data:
                break
            request = json.loads(data)

            if request['action'] == 'register':
                register_user(request, client_socket)
            elif request['action'] == 'login':
                # Sửa login_user để trả về user_id nếu thành công
                user_id = login_user(request, client_socket)
                if user_id:
                    user_sockets[user_id] = client_socket
            elif request['action'] == 'logout':
                if user_id:
                    logout_user(user_id)
                    if user_id in user_sockets:
                        del user_sockets[user_id]
                    client_socket.send("Logout successful.".encode())
                    break  # Thoát khỏi vòng lặp, đóng kết nối
                else:
                    client_socket.send("You are not logged in.".encode())
            elif request['action'] == 'send_message':
                send_message(request, client_socket)
            elif request['action'] == 'receive_message':
                receive_messages(request, client_socket)
            elif request['action'] == 'create_chat_room':
                create_chat_room(request, client_socket)
            elif request['action'] == 'join_chat_room':
                join_chat_room(request, client_socket)
            elif request['action'] == 'show_chat_rooms':
                show_chat_rooms(request, client_socket)
            elif request['action'] == 'send_friend_request':
                send_friend_request(request, client_socket)
            elif request['action'] == 'accept_friend_request':
                accept_friend_request(request, client_socket)
            elif request['action'] == 'show_friends':
                show_friends(request, client_socket)
    except Exception as e:
        print(f"Error: {e}")
    finally:
     if user_id and user_id in user_sockets:
        del user_sockets[user_id]
        # Cập nhật status offline
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'offline' WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
     client_socket.close()

# Hàm đăng ký người dùng
def register_user(request, client_socket):
    try:
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
    except Exception as e:
        print(f"Error during registration: {e}")
        client_socket.send("An error occurred during registration.".encode())
    finally:
        conn.close()

# Hàm đăng nhập người dùng
def login_user(request, client_socket):
    try:
        username = request['username']
        password = hash_password(request['password'])

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()

        if user:
            cursor.execute("UPDATE users SET status = 'online' WHERE user_id = %s", (user[0],))
            conn.commit()
            client_socket.send("Login successful.".encode())
            return user[0]  # Trả về user_id
        else:
            client_socket.send("Invalid username or password.".encode())
            return None
    except Exception as e:
        print(f"Error during login: {e}")
        client_socket.send("An error occurred during login.".encode())
        return None
    finally:
        conn.close()

# Hàm xử lý logout
def logout_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Cập nhật trạng thái thành offline khi người dùng logout
    cursor.execute("UPDATE users SET status = 'offline' WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

# Gửi tin nhắn trong phòng chat
def send_message(request, client_socket):
    sender_id = request['sender_id']
    content = request['content']
    room_id = request['room_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Lưu tin nhắn vào bảng messages với thời gian gửi (send_at)
    cursor.execute("INSERT INTO messages (sender_id, content, room_id, receiver_id) VALUES (%s, %s, %s, %s)", 
                   (sender_id, content, room_id, None)) # Chưa có receiver_id, có thể là null cho chat nhóm
    conn.commit()
    
    # Gửi tin nhắn tới tất cả thành viên trong phòng chat
    broadcast_message(room_id, content, sender_id)
    conn.close()


# Hàm nhận tin nhắn
def receive_messages(request, client_socket):
    user_id = request['user_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM messages WHERE receiver_id = %s OR room_id IN (SELECT room_id FROM room_members WHERE user_id = %s)", (user_id, user_id))
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

# Tạo phòng chat
def create_chat_room(request, client_socket):
    room_name = request['room_name']
    creator_id = request['creator_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tạo phòng chat mới
    cursor.execute("INSERT INTO chat_rooms (room_name, created_by) VALUES (%s, %s)", 
                   (room_name, creator_id))
    conn.commit()
    
    room_id = cursor.lastrowid  # Lấy ID phòng vừa tạo
    
    # Thêm người tạo phòng vào thành viên của phòng
    cursor.execute("INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)", 
                   (room_id, creator_id, 'admin'))
    conn.commit()
    
    client_socket.send(f"Chat room '{room_name}' created successfully.".encode())
    conn.close()


# Tham gia phòng chat
def join_chat_room(request, client_socket):
    room_id = request['room_id']
    user_id = request['user_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Kiểm tra xem người dùng đã tham gia phòng chưa
    cursor.execute("SELECT * FROM room_members WHERE room_id = %s AND user_id = %s", (room_id, user_id))
    if cursor.fetchone():
        client_socket.send("You are already a member of this room.".encode())
        return
    
    # Thêm người dùng vào phòng
    cursor.execute("INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)", 
                   (room_id, user_id, 'member'))
    conn.commit()
    client_socket.send(f"Successfully joined room {room_id}.".encode())
    conn.close()

# Hiển thị danh sách phòng chat
def show_chat_rooms(request, client_socket):
    user_id = request['user_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT cr.room_id, cr.room_name FROM chat_rooms cr
        JOIN room_members rm ON cr.room_id = rm.room_id
        WHERE rm.user_id = %s
    """, (user_id,))
    
    rooms = cursor.fetchall()
    
    if rooms:
        rooms_list = [{"room_id": room[0], "room_name": room[1]} for room in rooms]
        client_socket.send(json.dumps({"chat_rooms": rooms_list}).encode())
    else:
        client_socket.send("You are not a member of any rooms.".encode())
    
    conn.close()


# Gửi yêu cầu kết bạn
def send_friend_request(request, client_socket):
    sender_id = request['sender_id']
    receiver_id = request['receiver_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Kiểm tra xem yêu cầu kết bạn đã tồn tại chưa
    cursor.execute("SELECT * FROM user_relationships WHERE (user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s)", 
                   (sender_id, receiver_id, receiver_id, sender_id))
    if cursor.fetchone():
        client_socket.send("Friend request already sent or already friends.".encode())
        return

    # Gửi yêu cầu kết bạn
    cursor.execute("INSERT INTO user_relationships (user1_id, user2_id, status) VALUES (%s, %s, 'pending')", 
                   (sender_id, receiver_id))
    conn.commit()
    client_socket.send("Friend request sent.".encode())
    conn.close()

# Chấp nhận yêu cầu kết bạn
def accept_friend_request(request, client_socket):
    sender_id = request['sender_id']
    receiver_id = request['receiver_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE user_relationships SET status = 'accepted' WHERE user1_id = %s AND user2_id = %s AND status = 'pending'", 
                   (sender_id, receiver_id))
    conn.commit()
    
    client_socket.send("Friend request accepted.".encode())
    conn.close()

# Hiển thị danh sách bạn bè
def show_friends(request, client_socket):
    user_id = request['user_id']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT u.id, u.username FROM users u
        JOIN user_relationships ur ON u.id = ur.user2_id
        WHERE ur.user1_id = %s AND ur.status = 'accepted'
    """, (user_id,))
    
    friends = cursor.fetchall()
    
    if friends:
        friends_list = [{"id": friend[0], "username": friend[1]} for friend in friends]
        client_socket.send(json.dumps({"friends": friends_list}).encode())
    else:
        client_socket.send("You have no friends.".encode())
    
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

# Global dictionary to store user sockets
user_sockets = {}

if __name__ == "__main__":
    start_server()
