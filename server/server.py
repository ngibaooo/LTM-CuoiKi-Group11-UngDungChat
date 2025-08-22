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
    """Gửi text có newline (framing theo dòng)."""
    try:
        client_socket.sendall((text + "\n").encode("utf-8"))
    except:
        pass

def _send_json(client_socket, obj: dict):
    """Gửi JSON + newline (framing theo dòng)."""
    try:
        client_socket.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except:
        pass

# ------------------ Presence notify ------------------
def notify_friends_presence(user_id: int, new_status: str):
    """Đẩy realtime 'presence_update' cho toàn bộ bạn bè đã kết bạn (nếu họ đang online)."""
    conn = get_connection()
    if not conn:
        return
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.user_id
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
        for (fid,) in rows:
            sock = user_sockets.get(fid)
            if sock:
                _send_json(sock, {
                    "action": "presence_update",
                    "user_id": user_id,
                    "status": new_status
                })
    except Exception as e:
        print("notify_friends_presence error:", e)
    finally:
        _safe_close(cur, conn)

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
        cur.execute("SELECT display_name FROM users WHERE user_id = %s", (sender_id,))
        row = cur.fetchone()
        sender_name = row[0] if row else f"User {sender_id}"
        cur.execute("SELECT user_id FROM room_members WHERE room_id = %s", (room_id,))
        members = cur.fetchall()
        for (uid,) in members:
            if uid == sender_id:
                continue
            sock = user_sockets.get(uid)
            if sock:
                    _send_json(sock, {
                    "action": "receive_message",
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    **message
                })
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
        cur.execute(
            "INSERT INTO messages (sender_id, receiver_id, content, room_id, sent_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (sender_id, receiver_id, content, None),
        )
        conn.commit()

        cur.execute("SELECT sent_at FROM messages WHERE id = LAST_INSERT_ID()")
        (sent_at,) = cur.fetchone()
        ts = sent_at.isoformat(sep=" ") if hasattr(sent_at, "isoformat") else str(sent_at)

        msg_obj = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
            "sent_at": ts,
            "room_id": None
        }

        recv_sock = user_sockets.get(receiver_id)
        if recv_sock:
            _send_json(recv_sock, {"action": "receive_message", **msg_obj})

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
    conn = get_connection()
    if not conn:
        _send_text(client_socket, "Database connection failed.")
        return

    cur = None
    try:
        username = request["username"]
        password = hash_password(request["password"])
        email = request["email"]
        display_name = request.get("full_name")

        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            _send_text(client_socket, "Username already exists.")
            return
        cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            _send_text(client_socket, "Email already registered.")
            return
        cur.execute("SELECT 1 FROM users WHERE display_name = %s", (display_name,))
        if cur.fetchone():
            _send_text(client_socket, "Display name already registered.")
            return

        cur.execute(
            "INSERT INTO users (username, password, email, display_name, status) VALUES (%s, %s, %s, %s, %s)",
            (username, password, email, display_name, "offline"),
        )
        conn.commit()
        _send_text(client_socket, "Registration successful.")
    except Exception as e:
        print(f"Error during registration: {e}")
        _send_text(client_socket, "An error occurred during registration.")
    finally:
        _safe_close(cur, conn)

def login_user(request, client_socket):
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
            notify_friends_presence(user_id, "online")
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
        notify_friends_presence(user_id, "offline")
    except Exception as e:
        print("logout_user error:", e)
    finally:
        _safe_close(cur, conn)

def send_message(request, client_socket):
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
        cur.execute(
            "INSERT INTO messages (sender_id, content, room_id, receiver_id, sent_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (sender_id, content, room_id, None),
        )
        conn.commit()

        cur.execute("SELECT sent_at FROM messages WHERE id = LAST_INSERT_ID()")
        (sent_at,) = cur.fetchone()
        ts = sent_at.isoformat(sep=" ") if hasattr(sent_at, "isoformat") else str(sent_at)
        # lấy tên người gửi
        cur.execute("SELECT display_name FROM users WHERE user_id = %s", (sender_id,))
        row = cur.fetchone()
        sender_name = row[0] if row else f"User {sender_id}"
        message_obj = {
            "sender_id": sender_id,
            "sender_name": sender_name,
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
    """Lịch sử chung (DM đến mình + các phòng của mình)."""
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

def get_dm_history(request, client_socket):
    """Trả lịch sử DM giữa user_id và peer_id (2 chiều)."""
    me = request.get("user_id")
    peer = request.get("peer_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"action": "dm_history", "peer_id": peer, "messages": []})
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sender_id, receiver_id, content, sent_at
            FROM messages
            WHERE (sender_id = %s AND receiver_id = %s)
               OR (sender_id = %s AND receiver_id = %s)
            ORDER BY sent_at ASC
            LIMIT 300
            """,
            (me, peer, peer, me)
        )
        rows = cur.fetchall()
        out = []
        for s, r, c, t in rows:
            ts = t.isoformat(sep=" ") if hasattr(t, "isoformat") else str(t)
            out.append({"sender_id": s, "receiver_id": r, "content": c, "sent_at": ts})
        _send_json(client_socket, {"action": "dm_history", "peer_id": peer, "messages": out})
    except Exception as e:
        print("get_dm_history error:", e)
        _send_json(client_socket, {"action": "dm_history", "peer_id": peer, "messages": []})
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
        _send_text(client_socket, "Room name already exists.")
    finally:
        _safe_close(cur, conn)

def join_chat_room(request, client_socket):
    room_name = request.get("room_name")
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT room_id FROM chat_rooms WHERE room_name = %s", (room_name,))
        row = cur.fetchone()
        if not row:
            _send_text(client_socket, f"Room '{room_name}' is not exist.")
            return
        room_id = row[0]

        cur.execute("SELECT 1 FROM room_members WHERE room_id = %s AND user_id = %s", (room_id, user_id))
        if cur.fetchone():
            _send_text(client_socket, f"You have joined the room '{room_name}' already.")
            return

        cur.execute(
            "INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)",
            (room_id, user_id, "member"),
        )
        conn.commit()
        _send_text(client_socket, f"Participate in the room '{room_name}' successfully.")
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
    receiver_name = request.get("receiver_name")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE display_name = %s", (receiver_name,))
        row = cur.fetchone()
        if not row:
            _send_text(client_socket, f"User '{receiver_name}' is not exist.")
            return

        receiver_id = row[0]

        cur.execute("""
            SELECT 1 FROM user_relationships
            WHERE (user1_id = %s AND user2_id = %s)
               OR (user1_id = %s AND user2_id = %s)
        """, (sender_id, receiver_id, receiver_id, sender_id))
        if cur.fetchone():
            _send_text(client_socket, "Friend request already sent or already friends.")
            return

        cur.execute(
            "INSERT INTO user_relationships (user1_id, user2_id, status) VALUES (%s, %s, 'pending')",
            (sender_id, receiver_id),
        )
        conn.commit()
        _send_text(client_socket, "Friend request sent.")

        # Push realtime tới người nhận nếu đang online
        recv_sock = user_sockets.get(receiver_id)
        if recv_sock:
            cur.execute("SELECT display_name FROM users WHERE user_id = %s", (sender_id,))
            srow = cur.fetchone()
            sender_name = srow[0] if srow else f"User {sender_id}"
            _send_json(recv_sock, {
                "action": "friend_request",
                "sender_id": sender_id,
                "sender_name": sender_name
            })

    except Exception as e:
        print("send_friend_request error:", e)
        _send_text(client_socket, "Send friend request failed.")
    finally:
        _safe_close(cur, conn)

def accept_friend_request(request, client_socket):
    sender_name = request.get("sender_name")
    receiver_id = request.get("receiver_id")

    conn = get_connection()
    if not conn:
        _send_text(client_socket, "DB connect failed.")
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE display_name = %s", (sender_name,))
        row = cur.fetchone()
        if not row:
            _send_text(client_socket, f"User '{sender_name}' is not exist.")
            return

        sender_id = row[0]

        cur.execute(
            "UPDATE user_relationships SET status = 'accepted' "
            "WHERE user1_id = %s AND user2_id = %s AND status = 'pending'",
            (sender_id, receiver_id),
        )
        conn.commit()
        _send_text(client_socket, "Friend request accepted.")
    except Exception as e:
        print("accept_friend_request error:", e)
        _send_text(client_socket, "Accept friend request failed.")
    finally:
        _safe_close(cur, conn)

def show_friend_requests(request, client_socket):
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"requests": []})
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.user_id, u.display_name
            FROM users u
            JOIN user_relationships ur
              ON u.user_id = ur.user1_id
            WHERE ur.user2_id = %s AND ur.status = 'pending'
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        requests = [{"id": r[0], "display_name": r[1]} for r in rows]
        _send_json(client_socket, {"requests": requests})
    except Exception as e:
        print("show_friend_requests error:", e)
        _send_json(client_socket, {"requests": []})
    finally:
        _safe_close(cur, conn)

def show_friends(request, client_socket):
    """Trả về: id, display_name, status (online/offline)"""
    user_id = request.get("user_id")

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"friends": []})
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.user_id, u.display_name, u.status
            FROM users u
            JOIN user_relationships ur
              ON (
                   (u.user_id = ur.user2_id AND ur.user1_id = %s)
                OR (u.user_id = ur.user1_id AND ur.user2_id = %s)
                 )
            WHERE ur.status = 'accepted'
            ORDER BY u.display_name
            """,
            (user_id, user_id),
        )
        rows = cur.fetchall()
        friends = [{"id": r[0], "display_name": r[1], "status": r[2]} for r in rows]
        _send_json(client_socket, {"friends": friends})

    except Exception as e:
        print("show_friends error:", e)
        _send_json(client_socket, {"friends": []})
    finally:
        _safe_close(cur, conn)
    
def get_room_history(request, client_socket):
    """Trả lịch sử chat của 1 phòng (room_id)."""
    room_id = request.get("room_id")
    if not room_id:
        _send_json(client_socket, {"action": "room_history", "room_id": room_id, "messages": []})
        return

    conn = get_connection()
    if not conn:
        _send_json(client_socket, {"action": "room_history", "room_id": room_id, "messages": []})
        return

    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.sender_id, u.display_name, m.content, m.sent_at
            FROM messages m
            JOIN users u ON m.sender_id = u.user_id
            WHERE m.room_id = %s
            ORDER BY m.sent_at ASC
            LIMIT 300
            """,
            (room_id,)
        )
        rows = cur.fetchall()
        out = []
        for s, name, c, t in rows:
            ts = t.isoformat(sep=" ") if hasattr(t, "isoformat") else str(t)
            out.append({"sender_id": s, "sender_name": name, "content": c, "sent_at": ts})
        _send_json(client_socket, {"action": "room_history", "room_id": room_id, "messages": out})
    except Exception as e:
        print("get_room_history error:", e)
        _send_json(client_socket, {"action": "room_history", "room_id": room_id, "messages": []})
    finally:
        _safe_close(cur, conn)


# ------------------ Client loop ------------------
def handle_client(client_socket):
    user_id = None
    try:
        buffer = ""
        while True:
            chunk = client_socket.recv(4096).decode("utf-8", errors="ignore")
            if not chunk:
                break
            buffer += chunk

            # Xử lý theo dòng (1 dòng = 1 JSON)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    request = json.loads(line)
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
                        return
                    else:
                        _send_text(client_socket, "You are not logged in.")

                elif action == "send_message":
                    send_message(request, client_socket)

                elif action == "send_private_message":
                    send_private_message(request, client_socket)

                elif action == "receive_message":
                    receive_messages(request, client_socket)

                elif action == "get_dm_history":
                    get_dm_history(request, client_socket)

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
                elif action == "get_room_history":
                    get_room_history(request, client_socket)

                elif action == "show_friend_requests":
                    show_friend_requests(request, client_socket)

                else:
                    _send_text(client_socket, f"Unknown action: {action}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            if user_id:
                user_sockets.pop(user_id, None)
                conn = get_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE users SET status = 'offline' WHERE user_id = %s", (user_id,))
                    conn.commit()
                    _safe_close(cur, conn)
                notify_friends_presence(user_id, "offline")
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
