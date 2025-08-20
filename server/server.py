import socket
import threading
import json
from hashlib import sha256
from database import get_connection

# Lưu socket theo user_id sau khi đăng nhập
user_sockets = {}

# ------------------ Helpers ------------------
def hash_password(password: str) -> str:
    return sha256(password.encode()).hexdigest()

def _safe_close(cur=None, conn=None):
    try:
        if cur:
            cur.close()
    except:
        pass
    try:
        if conn:
            conn.close()
    except:
        pass

def _send_text(client_socket, text: str):
    try:
        client_socket.send(text.encode())
    except:
        pass

def _send_json(client_socket, obj: dict):
    try:
        client_socket.send(json.dumps(obj).encode())
    except:
        pass

# ------------------ Broadcast / Private ------------------
def broadcast_message(room_id: int, message: dict, sender_id: int):
    """Gửi message (JSON) tới tất cả thành viên phòng (trừ người gửi)."""
    conn = get_connection()
    if not conn:
        print("broadcast_message: DB connect failed")
        return
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM room_members WHERE room_id = %s", (room_id,))
        members = cur.fetchall()
        for (uid,) in members:
            if uid == sender_id:
                continue
            sock = user_sockets.get(uid)
            if sock:
                # Gửi đầy đủ thông tin message kèm action
                _send_json(sock, {"action": "receive_message", **message})
    except Exception as e:
        print("broadcast_message error:", e)
    finally:
        _safe_close(cur, conn)

def send_private_message(request, client_socket):
    """Gửi DM: lưu DB và push realtime cho receiver (nếu online)."""
    sender_id = request.get("sender_id")
    receiver_id = request.get("receiver_id")
    content = request.get("content", "")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {
            "action": "send_private_result",
            "ok": False,
            "error": "db_connect_failed"
        })
        return

    cur = None
    try:
        cur = conn.cursor()
        # Lưu message (room_id = NULL, có receiver_id, có sent_at)
        cur.execute(
            "INSERT INTO messages (sender_id, receiver_id, content, room_id, sent_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (sender_id, receiver_id, content, None),
        )
        conn.commit()

        # Lấy sent_at vừa insert
        cur.execute("SELECT sent_at FROM messages WHERE id = LAST_INSERT_ID()")
        (sent_at,) = cur.fetchone()
        ts = sent_at.isoformat(sep=" ") if hasattr(sent_at, "isoformat") else str(sent_at)

        # Payload chung cho cả sender & receiver
        msg_obj = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
            "sent_at": ts,
            "room_id": None
        }

        # Push realtime cho người nhận nếu đang online
        recv_sock = user_sockets.get(receiver_id)
        if recv_sock:
            _send_json(recv_sock, {"action": "receive_message", **msg_obj})

        # Phản hồi cho người gửi
        _send_json(client_socket, {
            "action": "send_private_result",
            "ok": True,
            **msg_obj
        })

    except Exception as e:
        print("send_private_message error:", e)
        _send_json(client_socket, {
            "action": "send_private_result",
            "ok": False,
            "error": "exception"
        })
    finally:
        _safe_close(cur, conn)

# ------------------ Handlers ------------------
def register_user(request, client_socket):
    """Giữ phản hồi dạng text để khớp client.register() hiện tại."""
    conn = get_connection()
    if not conn:
        _send_text(client_socket, "Database connection failed.")
        return

    cur = None
    try:
        username = request["username"]
        password = hash_password(request["password"])
        email = request["email"]

        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            _send_text(client_socket, "Username already exists.")
            return

        cur.execute(
            "INSERT INTO users (username, password, email, status) VALUES (%s, %s, %s, 'offline')",
            (username, password, email),
        )
        conn.commit()
        _send_text(client_socket, "Registration successful.")
    except Exception as e:
        print(f"Error during registration: {e}")
        _send_text(client_socket, "An error occurred during registration.")
    finally:
        _safe_close(cur, conn)

def login_user(request, client_socket):
    """Trả JSON rõ ràng để client.parse."""
    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"action": "login_result", "ok": False, "error": "db_connect_failed"})
        return None

    cur = None
    try:
        username = request["username"]
        password = hash_password(request["password"])

        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE username = %s AND password = %s", (username, password))
        row = cur.fetchone()

        if row:
            user_id = row[0]
            cur.execute("UPDATE users SET status = 'online' WHERE user_id = %s", (user_id,))
            conn.commit()
            _send_json(client_socket, {
                "action": "login_result",
                "ok": True,
                "user_id": user_id,
                "username": username
            })
            return user_id
        else:
            _send_json(client_socket, {"action": "login_result", "ok": False, "error": "invalid_credentials"})
            return None
    except Exception as e:
        print(f"Error during login: {e}")
        _send_json(client_socket, {"action": "login_result", "ok": False, "error": "exception"})
        return None
    finally:
        _safe_close(cur, conn)

def logout_user(user_id: int):
    conn = get_connection()
    if not conn:
        return
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'offline' WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        print("logout_user error:", e)
    finally:
        _safe_close(cur, conn)

def send_message(request, client_socket):
    """Gửi tin nhắn vào phòng + broadcast kèm thời gian."""
    sender_id = request.get("sender_id")
    content = request.get("content", "")
    room_id = request.get("room_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {
            "action": "send_message_result",
            "ok": False,
            "error": "db_connect_failed"
        })
        return

    cur = None
    try:
        cur = conn.cursor()
        # Thêm tin nhắn với thời gian gửi
        cur.execute(
            "INSERT INTO messages (sender_id, content, room_id, receiver_id, sent_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (sender_id, content, room_id, None),
        )
        conn.commit()

        # Lấy sent_at vừa insert
        cur.execute("SELECT sent_at FROM messages WHERE id = LAST_INSERT_ID()")
        (sent_at,) = cur.fetchone()
        ts = sent_at.isoformat(sep=" ") if hasattr(sent_at, "isoformat") else str(sent_at)

        # Tạo payload để broadcast
        message_obj = {
            "sender_id": sender_id,
            "content": content,
            "sent_at": ts,
            "room_id": room_id
        }

        broadcast_message(room_id, message_obj, sender_id)

        _send_json(client_socket, {
            "action": "send_message_result",
            "ok": True,
            "sent_at": ts
        })
    except Exception as e:
        print("send_message error:", e)
        _send_json(client_socket, {
            "action": "send_message_result",
            "ok": False,
            "error": "exception"
        })
    finally:
        _safe_close(cur, conn)

def receive_messages(request, client_socket):
    """Trả lịch sử tin nhắn liên quan (DM hoặc phòng đã tham gia)."""
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, [])
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, sender_id, receiver_id, content, sent_at, room_id
            FROM messages
            WHERE receiver_id = %s
               OR room_id IN (SELECT room_id FROM room_members WHERE user_id = %s)
            ORDER BY sent_at DESC
            LIMIT 200
            """,
            (user_id, user_id),
        )
        rows = cur.fetchall()

        message_list = []
        for r in rows:
            _id, sender_id, receiver_id, content, sent_at, room_id = r
            # JSON hóa thời gian an toàn
            ts = sent_at.isoformat(sep=" ") if hasattr(sent_at, "isoformat") else str(sent_at)
            message_list.append({
                "id": _id,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
                "sent_at": ts,
                "room_id": room_id
            })
        _send_json(client_socket, message_list)
    except Exception as e:
        print("receive_messages error:", e)
        _send_json(client_socket, [])
    finally:
        _safe_close(cur, conn)

def create_chat_room(request, client_socket):
    room_name = request.get("room_name", "")
    creator_id = request.get("creator_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO chat_rooms (room_name, created_by) VALUES (%s, %s)", (room_name, creator_id))
        conn.commit()
        room_id = cur.lastrowid
        cur.execute("INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)",
                    (room_id, creator_id, "admin"))
        conn.commit()
        _send_text(client_socket, f"Chat room '{room_name}' created successfully.")
    except Exception as e:
        print("create_chat_room error:", e)
        _send_text(client_socket, "Create room failed.")
    finally:
        _safe_close(cur, conn)

def join_chat_room(request, client_socket):
    room_id = request.get("room_id")
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM room_members WHERE room_id = %s AND user_id = %s", (room_id, user_id))
        if cur.fetchone():
            _send_text(client_socket, "You are already a member of this room.")
            return
        cur.execute(
            "INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)",
            (room_id, user_id, "member"),
        )
        conn.commit()
        _send_text(client_socket, f"Successfully joined room {room_id}.")
    except Exception as e:
        print("join_chat_room error:", e)
        _send_text(client_socket, "Join room failed.")
    finally:
        _safe_close(cur, conn)

def show_chat_rooms(request, client_socket):
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"chat_rooms": []})
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cr.room_id, cr.room_name
            FROM chat_rooms cr
            JOIN room_members rm ON cr.room_id = rm.room_id
            WHERE rm.user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        rooms = [{"room_id": r[0], "room_name": r[1]} for r in rows]
        _send_json(client_socket, {"chat_rooms": rooms})
    except Exception as e:
        print("show_chat_rooms error:", e)
        _send_json(client_socket, {"chat_rooms": []})
    finally:
        _safe_close(cur, conn)

def send_friend_request(request, client_socket):
    sender_id = request.get("sender_id")
    receiver_id = request.get("receiver_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM user_relationships
            WHERE (user1_id = %s AND user2_id = %s)
               OR (user1_id = %s AND user2_id = %s)
            """,
            (sender_id, receiver_id, receiver_id, sender_id),
        )
        if cur.fetchone():
            _send_text(client_socket, "Friend request already sent or already friends.")
            return

        cur.execute(
            "INSERT INTO user_relationships (user1_id, user2_id, status) VALUES (%s, %s, 'pending')",
            (sender_id, receiver_id),
        )
        conn.commit()
        _send_text(client_socket, "Friend request sent.")
    except Exception as e:
        print("send_friend_request error:", e)
        _send_text(client_socket, "Send friend request failed.")
    finally:
        _safe_close(cur, conn)

def accept_friend_request(request, client_socket):
    sender_id = request.get("sender_id")
    receiver_id = request.get("receiver_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_relationships SET status = 'accepted' WHERE user1_id = %s AND user2_id = %s AND status = 'pending'",
            (sender_id, receiver_id),
        )
        conn.commit()
        _send_text(client_socket, "Friend request accepted.")
    except Exception as e:
        print("accept_friend_request error:", e)
        _send_text(client_socket, "Accept friend request failed.")
    finally:
        _safe_close(cur, conn)

def show_friends(request, client_socket):
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"friends": []})
        return

    cur = None
    try        :
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.user_id, u.username
            FROM users u
            JOIN user_relationships ur
              ON (
                (u.user_id = ur.user2_id AND ur.user1_id = %s)
              OR (u.user_id = ur.user1_id AND ur.user2_id = %s)
              )
            WHERE ur.status = 'accepted'
            """,
            (user_id, user_id),
        )
        rows = cur.fetchall()
        friends = [{"id": r[0], "username": r[1]} for r in rows]
        _send_json(client_socket, {"friends": friends})
    except Exception as e:
        print("show_friends error:", e)
        _send_json(client_socket, {"friends": []})
    finally:
        _safe_close(cur, conn)

# ------------------ Client loop ------------------
def handle_client(client_socket):
    user_id = None
    try:
        while True:
            data = client_socket.recv(4096).decode()
            if not data:
                break
            try:
                request = json.loads(data)
            except json.JSONDecodeError:
                _send_text(client_socket, "Invalid JSON payload.")
                continue

            action = request.get("action")

            if action == "register":
                register_user(request, client_socket)

            elif action == "login":
                user_id = login_user(request, client_socket)
                if user_id:
                    user_sockets[user_id] = client_socket

            elif action == "logout":
                if user_id:
                    logout_user(user_id)
                    user_sockets.pop(user_id, None)
                    _send_text(client_socket, "Logout successful.")
                    break
                else:
                    _send_text(client_socket, "You are not logged in.")

            elif action == "send_message":
                send_message(request, client_socket)

            elif action == "send_private_message":
                send_private_message(request, client_socket)

            elif action == "receive_message":
                receive_messages(request, client_socket)

            elif action == "create_chat_room":
                create_chat_room(request, client_socket)

            elif action == "join_chat_room":
                join_chat_room(request, client_socket)

            elif action == "show_chat_rooms":
                show_chat_rooms(request, client_socket)

            elif action == "send_friend_request":
                send_friend_request(request, client_socket)

            elif action == "accept_friend_request":
                accept_friend_request(request, client_socket)

            elif action == "show_friends":
                show_friends(request, client_socket)

            else:
                _send_text(client_socket, f"Unknown action: {action}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # cleanup khi client rời đi
        try:
            if user_id:
                user_sockets.pop(user_id, None)
                conn = get_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE users SET status = 'offline' WHERE user_id = %s", (user_id,))
                    conn.commit()
                    _safe_close(cur, conn)
        except Exception as e:
            print("offline update error:", e)
        try:
            client_socket.close()
        except:
            pass

# ------------------ Server bootstrap ------------------
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", 5000))
    server.listen(5)
    print("Server started on port 5000...")

    while True:
        client_socket, client_address = server.accept()
        print(f"New connection from {client_address}")
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()

if __name__ == "__main__":
    start_server()
