#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Server TCP cho Ứng dụng Chat Socket (đa luồng, JSON theo dòng)
- Hỗ trợ các action phía client:
  register, login, get_friend_list, search_users, send_friend_request,
  respond_friend_request, remove_friend,
  create_room, join_room, leave_room, invite_to_room,
  send_message, typing
- Đẩy sự kiện (event): message, presence_update, friend_request, friend_update, room_update
- Lưu trữ nhẹ: bộ nhớ + file server_data.json

CHẠY:
    python server.py --host 0.0.0.0 --port 9009
"""

import json
import os
import socket
import threading
import argparse
import time

DATA_FILE = "server_data.json"

# ======================== Kho dữ liệu (in-memory) ========================
class DataStore:
    def __init__(self):
        # users: username -> {"password": str, "friends": set[str], "friend_requests_inbox": set[str], "rooms": set[str]}
        self.users = {}
        # rooms: room_id(str) -> {"room_id": str, "room_name": str, "members": set[str]}
        self.rooms = {}
        self.next_room_id = 1000
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f)
            with self.lock:
                self.users = {u: {
                    "password": v.get("password",""),
                    "friends": set(v.get("friends", [])),
                    "friend_requests_inbox": set(v.get("friend_requests_inbox", [])),
                    "rooms": set(v.get("rooms", [])),
                } for u, v in obj.get("users", {}).items()}
                self.rooms = {rid: {
                    "room_id": rid,
                    "room_name": r.get("room_name", rid),
                    "members": set(r.get("members", [])),
                } for rid, r in obj.get("rooms", {}).items()}
                self.next_room_id = int(obj.get("next_room_id", 1000))
        except Exception as e:
            print("Load data error:", e)

    def _save(self):
        try:
            obj = {
                "users": {u: {
                    "password": v["password"],
                    "friends": sorted(list(v["friends"])),
                    "friend_requests_inbox": sorted(list(v["friend_requests_inbox"])),
                    "rooms": sorted(list(v["rooms"]))
                } for u, v in self.users.items()},
                "rooms": {rid: {
                    "room_name": r["room_name"],
                    "members": sorted(list(r["members"]))
                } for rid, r in self.rooms.items()},
                "next_room_id": self.next_room_id
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Save data error:", e)

    # ---------- User ops ----------
    def register_user(self, username, password):
        with self.lock:
            if username in self.users:
                return False, "Username đã tồn tại"
            self.users[username] = {
                "password": password,
                "friends": set(),
                "friend_requests_inbox": set(),
                "rooms": set()
            }
            self._save()
        return True, "OK"

    def check_login(self, username, password):
        with self.lock:
            u = self.users.get(username)
            if not u or u["password"] != password:
                return False
        return True

    def list_friends(self, username):
        with self.lock:
            u = self.users.get(username, {})
            return sorted(list(u.get("friends", set())))

    def add_friends_mutual(self, a, b):
        with self.lock:
            if a in self.users and b in self.users:
                self.users[a]["friends"].add(b)
                self.users[b]["friends"].add(a)
                # xóa request nếu còn
                if a in self.users[b]["friend_requests_inbox"]:
                    self.users[b]["friend_requests_inbox"].discard(a)
                if b in self.users[a]["friend_requests_inbox"]:
                    self.users[a]["friend_requests_inbox"].discard(b)
                self._save()

    def remove_friend(self, a, b):
        with self.lock:
            if a in self.users:
                self.users[a]["friends"].discard(b)
            if b in self.users:
                self.users[b]["friends"].discard(a)
            self._save()

    def add_friend_request(self, to_user, from_user):
        with self.lock:
            if to_user in self.users and from_user in self.users:
                # nếu đã là bạn thì bỏ qua
                if from_user in self.users[to_user]["friends"]:
                    return
                self.users[to_user]["friend_requests_inbox"].add(from_user)
                self._save()

    def get_friend_requests_inbox(self, username):
        with self.lock:
            return sorted(list(self.users.get(username, {}).get("friend_requests_inbox", set())))

    def clear_friend_request(self, to_user, from_user):
        with self.lock:
            if to_user in self.users:
                self.users[to_user]["friend_requests_inbox"].discard(from_user)
                self._save()

    # ---------- Search ----------
    def search_users(self, query, exclude=None):
        exclude = exclude or set()
        q = (query or "").lower()
        with self.lock:
            res = [u for u in self.users.keys() if q in u.lower() and u not in exclude]
        return sorted(res)

    # ---------- Room ops ----------
    def create_room(self, creator, name):
        with self.lock:
            rid = str(self.next_room_id)
            self.next_room_id += 1
            self.rooms[rid] = {"room_id": rid, "room_name": name or rid, "members": set([creator])}
            if creator in self.users:
                self.users[creator]["rooms"].add(rid)
            self._save()
            return rid

    def join_room(self, username, room_id):
        with self.lock:
            r = self.rooms.get(room_id)
            if not r:
                return False, "Room không tồn tại"
            r["members"].add(username)
            if username in self.users:
                self.users[username]["rooms"].add(room_id)
            self._save()
        return True, "OK"

    def leave_room(self, username, room_id):
        with self.lock:
            r = self.rooms.get(room_id)
            if not r:
                return False, "Room không tồn tại"
            r["members"].discard(username)
            if username in self.users:
                self.users[username]["rooms"].discard(room_id)
            self._save()
        return True, "OK"

    def invite_to_room(self, inviter, room_id, target_user):
        with self.lock:
            r = self.rooms.get(room_id)
            if not r:
                return False, "Room không tồn tại"
            if inviter not in r["members"]:
                return False, "Bạn không ở trong room"
            # auto-join đơn giản (hoặc bạn có thể tạo luồng “lời mời room” riêng)
            r["members"].add(target_user)
            if target_user in self.users:
                self.users[target_user]["rooms"].add(room_id)
            self._save()
        return True, "OK"

    def list_rooms_of(self, username):
        with self.lock:
            ids = sorted(list(self.users.get(username, {}).get("rooms", set())))
            return [{"room_id": rid, "room_name": self.rooms[rid]["room_name"]} for rid in ids if rid in self.rooms]

    def room_name(self, room_id):
        with self.lock:
            r = self.rooms.get(room_id)
            return r["room_name"] if r else room_id

    def members_of_room(self, room_id):
        with self.lock:
            r = self.rooms.get(room_id)
            return set(r["members"]) if r else set()


# ======================== Quản lý kết nối Client ========================
class ClientConn:
    def __init__(self, sock, addr, server):
        self.sock = sock
        self.addr = addr
        self.server = server
        self.file_lock = threading.Lock()  # serialize sendall
        self.username = None
        self.alive = True
        self.buf = b""

    def send_obj(self, obj: dict):
        try:
            data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
            with self.file_lock:
                self.sock.sendall(data)
        except Exception as e:
            print("send_obj error:", e)
            self.close()

    def send_response(self, req_id, action, ok=True, message="OK", data=None):
        self.send_obj({
            "type": "response",
            "req_id": req_id,
            "action": action,
            "ok": bool(ok),
            "message": message,
            "data": data or {}
        })

    def send_event(self, event, data):
        self.send_obj({
            "type": "event",
            "event": event,
            "data": data or {}
        })

    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        # cập nhật presence
        if self.username:
            self.server.set_offline(self.username)


# ======================== Server chính ========================
class ChatServer:
    def __init__(self, host, port):
        self.ds = DataStore()
        self.host = host
        self.port = port
        self.sock = None
        # online: username -> ClientConn
        self.online = {}
        self.online_lock = threading.Lock()

    # ---------- Presence ----------
    def set_online(self, username, conn: ClientConn):
        with self.online_lock:
            self.online[username] = conn
        self.broadcast_presence(username, True)

    def set_offline(self, username):
        with self.online_lock:
            if username in self.online:
                del self.online[username]
        self.broadcast_presence(username, False)

    def is_online(self, username):
        with self.online_lock:
            return username in self.online

    # ---------- Broadcast helpers ----------
    def broadcast_presence(self, username, online):
        # gửi cho tất cả bạn bè của username (và chính họ)
        friends = self.ds.list_friends(username)
        targets = set(friends + [username])
        evt = {"username": username, "online": bool(online)}
        self._multicast_event(targets, "presence_update", evt)

    def broadcast_friend_update(self, username):
        # gửi full friend list cho chính user (và có thể cho bạn bè nếu muốn)
        friends_data = [{"username": u, "online": self.is_online(u)} for u in self.ds.list_friends(username)]
        evt = {"friends": friends_data}
        self._unicast_event(username, "friend_update", evt)

    def broadcast_room_update(self, username):
        rooms = self.ds.list_rooms_of(username)
        evt = {"rooms": rooms}
        self._unicast_event(username, "room_update", evt)

    def _unicast_event(self, username, event, data):
        with self.online_lock:
            conn = self.online.get(username)
        if conn:
            conn.send_event(event, data)

    def _multicast_event(self, usernames, event, data):
        with self.online_lock:
            conns = [self.online.get(u) for u in usernames if u in self.online]
        for c in conns:
            if c:
                c.send_event(event, data)

    # ---------- Networking ----------
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(100)
        print(f"Server listening on {self.host}:{self.port}")
        while True:
            client_sock, addr = self.sock.accept()
            conn = ClientConn(client_sock, addr, self)
            th = threading.Thread(target=self.handle_client, args=(conn,), daemon=True)
            th.start()

    def handle_client(self, conn: ClientConn):
        try:
            while conn.alive:
                chunk = conn.sock.recv(4096)
                if not chunk:
                    break
                conn.buf += chunk
                while b"\n" in conn.buf:
                    line, conn.buf = conn.buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                        self._handle_message(conn, obj)
                    except Exception as e:
                        print("parse error:", e)
        except Exception as e:
            print("client error:", e)
        finally:
            conn.close()

    # ---------- Xử lý request ----------
    def _handle_message(self, conn: ClientConn, obj: dict):
        if obj.get("type") != "request":
            return
        req_id = obj.get("req_id")
        action = obj.get("action")

        # Map hành động
        if action == "register":
            self._act_register(conn, req_id, obj)
        elif action == "login":
            self._act_login(conn, req_id, obj)
        else:
            # các action yêu cầu đã đăng nhập
            if not conn.username:
                conn.send_response(req_id, action, ok=False, message="Chưa đăng nhập")
                return
            if action == "get_friend_list":
                self._act_get_friend_list(conn, req_id, obj)
            elif action == "search_users":
                self._act_search_users(conn, req_id, obj)
            elif action == "send_friend_request":
                self._act_send_friend_request(conn, req_id, obj)
            elif action == "respond_friend_request":
                self._act_respond_friend_request(conn, req_id, obj)
            elif action == "remove_friend":
                self._act_remove_friend(conn, req_id, obj)
            elif action == "create_room":
                self._act_create_room(conn, req_id, obj)
            elif action == "join_room":
                self._act_join_room(conn, req_id, obj)
            elif action == "leave_room":
                self._act_leave_room(conn, req_id, obj)
            elif action == "invite_to_room":
                self._act_invite_to_room(conn, req_id, obj)
            elif action == "send_message":
                self._act_send_message(conn, req_id, obj)
            elif action == "typing":
                self._act_typing(conn, req_id, obj)
            else:
                conn.send_response(req_id, action, ok=False, message="Action không hỗ trợ")

    # ----- Implementations -----
    def _act_register(self, conn, req_id, obj):
        username = (obj.get("username") or "").strip()
        password = obj.get("password") or ""
        if not username or not password:
            conn.send_response(req_id, "register", ok=False, message="Thiếu username/password")
            return
        ok, msg = self.ds.register_user(username, password)
        conn.send_response(req_id, "register", ok=ok, message=msg)

    def _act_login(self, conn, req_id, obj):
        username = (obj.get("username") or "").strip()
        password = obj.get("password") or ""
        if not self.ds.check_login(username, password):
            conn.send_response(req_id, "login", ok=False, message="Sai thông tin đăng nhập")
            return
        # set online
        conn.username = username
        self.set_online(username, conn)

        # payload ban đầu
        friends = self.ds.list_friends(username)
        friends_data = [{"username": u, "online": self.is_online(u)} for u in friends]
        rooms = self.ds.list_rooms_of(username)
        inbox = self.ds.get_friend_requests_inbox(username)
        data = {
            "username": username,
            "token": None,  # có thể sinh JWT nếu muốn
            "friends": friends_data,
            "rooms": rooms,
            "friend_requests_inbox": inbox
        }
        conn.send_response(req_id, "login", ok=True, data=data, message="OK")

    def _act_get_friend_list(self, conn, req_id, obj):
        username = conn.username
        friends = self.ds.list_friends(username)
        friends_data = [{"username": u, "online": self.is_online(u)} for u in friends]
        rooms = self.ds.list_rooms_of(username)
        conn.send_response(req_id, "get_friend_list", ok=True, data={"friends": friends_data, "rooms": rooms})

    def _act_search_users(self, conn, req_id, obj):
        q = obj.get("query") or ""
        res = self.ds.search_users(q, exclude={conn.username})
        conn.send_response(req_id, "search_users", ok=True, data={"users": res})

    def _act_send_friend_request(self, conn, req_id, obj):
        to_user = obj.get("to")
        if not to_user or to_user == conn.username:
            conn.send_response(req_id, "send_friend_request", ok=False, message="User không hợp lệ")
            return
        if to_user not in self.ds.users:
            conn.send_response(req_id, "send_friend_request", ok=False, message="Không tồn tại user")
            return
        self.ds.add_friend_request(to_user, conn.username)
        conn.send_response(req_id, "send_friend_request", ok=True, message="Đã gửi")

        # đẩy event đến người nhận
        self._unicast_event(to_user, "friend_request", {"from": conn.username})
        # và cập nhật friend_update cho người gửi (để đồng bộ)
        self.broadcast_friend_update(conn.username)

    def _act_respond_friend_request(self, conn, req_id, obj):
        from_user = obj.get("from")
        accept = bool(obj.get("accept"))
        if not from_user or from_user not in self.ds.users:
            conn.send_response(req_id, "respond_friend_request", ok=False, message="User không hợp lệ")
            return
        # xóa request
        self.ds.clear_friend_request(conn.username, from_user)
        if accept:
            self.ds.add_friends_mutual(conn.username, from_user)

        conn.send_response(req_id, "respond_friend_request", ok=True, message="OK")
        # đẩy cập nhật friend list cho cả 2
        self.broadcast_friend_update(conn.username)
        self.broadcast_friend_update(from_user)

    def _act_remove_friend(self, conn, req_id, obj):
        target = obj.get("username")
        if not target or target not in self.ds.users:
            conn.send_response(req_id, "remove_friend", ok=False, message="User không hợp lệ")
            return
        self.ds.remove_friend(conn.username, target)
        conn.send_response(req_id, "remove_friend", ok=True)
        # cập nhật cả 2 phía
        self.broadcast_friend_update(conn.username)
        self.broadcast_friend_update(target)

    def _act_create_room(self, conn, req_id, obj):
        name = (obj.get("room_name") or "").strip() or "Room"
        rid = self.ds.create_room(conn.username, name)
        data = {"room_id": rid, "room_name": name, "rooms": self.ds.list_rooms_of(conn.username)}
        conn.send_response(req_id, "create_room", ok=True, data=data)
        self.broadcast_room_update(conn.username)

    def _act_join_room(self, conn, req_id, obj):
        room_id = str(obj.get("room_id") or "")
        ok, msg = self.ds.join_room(conn.username, room_id)
        if not ok:
            conn.send_response(req_id, "join_room", ok=False, message=msg)
            return
        data = {"rooms": self.ds.list_rooms_of(conn.username)}
        conn.send_response(req_id, "join_room", ok=True, data=data)
        self.broadcast_room_update(conn.username)

    def _act_leave_room(self, conn, req_id, obj):
        room_id = str(obj.get("room_id") or "")
        ok, msg = self.ds.leave_room(conn.username, room_id)
        if not ok:
            conn.send_response(req_id, "leave_room", ok=False, message=msg)
            return
        data = {"rooms": self.ds.list_rooms_of(conn.username)}
        conn.send_response(req_id, "leave_room", ok=True, data=data)
        self.broadcast_room_update(conn.username)

    def _act_invite_to_room(self, conn, req_id, obj):
        room_id = str(obj.get("room_id") or "")
        username = obj.get("username")
        if not username or username not in self.ds.users:
            conn.send_response(req_id, "invite_to_room", ok=False, message="User không hợp lệ")
            return
        ok, msg = self.ds.invite_to_room(conn.username, room_id, username)
        if not ok:
            conn.send_response(req_id, "invite_to_room", ok=False, message=msg)
            return
        # cập nhật room list cho người được mời nếu online
        self.broadcast_room_update(username)
        # phản hồi cho người mời
        data = {"rooms": self.ds.list_rooms_of(conn.username)}
        conn.send_response(req_id, "invite_to_room", ok=True, data=data)

    def _act_send_message(self, conn, req_id, obj):
        to_type = obj.get("to_type")
        to_id = str(obj.get("to") or "")
        msg_type = obj.get("msg_type") or "text"
        content = obj.get("content") or ""
        filename = obj.get("filename")

        if to_type not in ("user", "room"):
            conn.send_response(req_id, "send_message", ok=False, message="to_type không hợp lệ")
            return

        ts = int(time.time())
        event_payload = {
            "from": conn.username,
            "to_type": to_type,
            "to": to_id,
            "msg_type": msg_type,
            "content": content,
            "filename": filename,
            "timestamp": ts
        }

        if to_type == "user":
            # gửi cho chính sender (echo) + người nhận nếu online
            targets = set([conn.username, to_id])
            self._multicast_event(targets, "message", event_payload)
        else:
            # room: gửi cho tất cả member đang online
            members = self.ds.members_of_room(to_id)
            self._multicast_event(members, "message", event_payload)

        conn.send_response(req_id, "send_message", ok=True)

    def _act_typing(self, conn, req_id, obj):
        to_type = obj.get("to_type")
        to_id = str(obj.get("to") or "")
        is_typing = bool(obj.get("is_typing"))
        payload = {
            "from": conn.username,
            "to_type": to_type,
            "to": to_id,
            "is_typing": is_typing,
            "timestamp": int(time.time())
        }
        if to_type == "user":
            self._unicast_event(to_id, "typing", payload)
        elif to_type == "room":
            members = self.ds.members_of_room(to_id) - {conn.username}
            self._multicast_event(members, "typing", payload)
        conn.send_response(req_id, "typing", ok=True)


# ======================== Main ========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9009)
    args = ap.parse_args()

    srv = ChatServer(args.host, args.port)
    try:
        srv.start()
    except KeyboardInterrupt:
        print("\nServer dừng.")


if __name__ == "__main__":
    main()
