import socket
import threading
import json
from database import get_connection

HOST = "127.0.0.1"
PORT = 5000

clients = {}  # conn -> user_id

# ------------------- Xử lý DB -------------------
def register_user(username, password, display_name, email=None, avatar=None):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO USERS (Username, Password, Display_name, Status, Email, Avatar)
                VALUES (%s, %s, %s, 'offline', %s, %s)
            """, (username, password, display_name, email, avatar))
            conn.commit()
            return True, "Đăng ký thành công!"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
    return False, "DB không kết nối được."

def login_user(username, password):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM USERS WHERE Username=%s AND Password=%s", (username, password))
            user = cursor.fetchone()
            if user:
                cursor.execute("UPDATE USERS SET Status='online' WHERE Id=%s", (user["Id"],))
                conn.commit()
                return True, user
            return False, "Sai username hoặc password."
        finally:
            conn.close()
    return False, "DB không kết nối được."

def logout_user(user_id):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE USERS SET Status='offline' WHERE Id=%s", (user_id,))
            conn.commit()
        finally:
            conn.close()

def create_room(room_name, user_id):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO CHAT_ROOM (Room_name, Created_by) VALUES (%s, %s)", (room_name, user_id))
            conn.commit()
            # add creator as admin
            cursor.execute("SELECT Id FROM CHAT_ROOM WHERE Room_name=%s", (room_name,))
            room_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO ROOM_MEMBER (Room_id, User_id, Role) VALUES (%s, %s, 'admin')", (room_id, user_id))
            conn.commit()
            return True, "Tạo phòng thành công!"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
    return False, "DB không kết nối được."

def join_room(room_id, user_id):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO ROOM_MEMBER (Room_id, User_id, Role) VALUES (%s, %s, 'member')", (room_id, user_id))
            conn.commit()
            return True, "Tham gia phòng thành công!"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
    return False, "DB không kết nối được."

def save_message(sender_id, content, room_id=None, receive_id=None):
    conn = get_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO MESSAGES (Sender_id, Receive_id, Room_id, Content, Status, Send_at)
                VALUES (%s, %s, %s, %s, 'sent', NOW())
            """, (sender_id, receive_id, room_id, content))
            conn.commit()
        except Exception as e:
            print("Lỗi lưu tin nhắn:", e)
        finally:
            conn.close()

# ------------------- Xử lý Client -------------------
def handle_client(conn, addr):
    print(f"[KẾT NỐI] {addr}")
    user_id = None
    try:
        while True:
            data = conn.recv(4096).decode("utf-8")
            if not data:
                break
            try:
                request = json.loads(data)
            except:
                conn.sendall(json.dumps({"status": False, "msg": "Sai format JSON"}).encode("utf-8"))
                continue

            action = request.get("action")
            response = {}

            if action == "register":
                ok, msg = register_user(request["username"], request["password"], request["display_name"],
                                        request.get("email"), request.get("avatar"))
                response = {"status": ok, "msg": msg}

            elif action == "login":
                ok, result = login_user(request["username"], request["password"])
                if ok:
                    user_id = result["Id"]
                    clients[conn] = user_id
                    response = {"status": True, "msg": "Đăng nhập thành công!", "user": result}
                else:
                    response = {"status": False, "msg": result}

            elif action == "logout":
                if user_id:
                    logout_user(user_id)
                    response = {"status": True, "msg": "Đăng xuất thành công"}
                    break

            elif action == "create_room":
                ok, msg = create_room(request["room_name"], user_id)
                response = {"status": ok, "msg": msg}

            elif action == "join_room":
                ok, msg = join_room(request["room_id"], user_id)
                response = {"status": ok, "msg": msg}

            elif action == "send_message":
                msg = request["msg"]
                room_id = request.get("room_id")
                receive_id = request.get("receive_id")
                save_message(user_id, msg, room_id, receive_id)
                response = {"status": True, "msg": msg, "sender": user_id}
                # broadcast cho tất cả client
                for c in clients:
                    if c != conn:
                        c.sendall(json.dumps(response).encode("utf-8"))

            else:
                response = {"status": False, "msg": "Hành động không hợp lệ"}

            conn.sendall(json.dumps(response).encode("utf-8"))

    except Exception as e:
        print(f"Lỗi client {addr}: {e}")
    finally:
        if user_id:
            logout_user(user_id)
            if conn in clients:
                del clients[conn]
        conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[SERVER] Đang chạy tại {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()
