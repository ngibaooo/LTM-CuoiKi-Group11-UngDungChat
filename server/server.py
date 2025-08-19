
import socket
import threading
import json
import os
import hashlib
import datetime
import random
from typing import Dict, Any, List, Tuple

HOST = "127.0.0.1"
PORT = 5555
DATA_FILE = "server_data.json"
LOCK = threading.RLock()

def now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def json_send(sock: socket.socket, obj: Dict[str, Any]):
    try:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        sock.sendall(data)
    except Exception:
        pass

def json_lines(fp):
    for line in fp:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue

def is_4digit(s: str) -> bool:
    return isinstance(s, str) and len(s) == 4 and s.isdigit()

class ChatServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port

        # persistent
        # users[u] = {
        #   "salt","pwd_hash","full_name",
        #   "friends": set(), "rooms": set(room_id),
        #   "incoming": set(), "outgoing": set(),
        #   "offline_queue": list()
        # }
        self.users: Dict[str, Dict[str, Any]] = {}   # username -> info
        # rooms keyed by room_id (4-digit string)
        # rooms[room_id] = {"id": room_id, "name": ..., "owner": ..., "members": set(), "messages": []}
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self.dm_messages: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

        # runtime
        self.online: Dict[str, socket.socket] = {}   # username -> socket
        self.sock2user: Dict[socket.socket, str] = {}

        self.load_data()

    # ---------- persistence ----------
    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # users
        self.users = {}
        for u, info in data.get("users", {}).items():
            info["friends"]  = set(info.get("friends", []))
            info["rooms"]    = set(info.get("rooms", []))
            info["incoming"] = set(info.get("incoming", []))
            info["outgoing"] = set(info.get("outgoing", []))
            info["full_name"] = info.get("full_name") or u
            self.users[u] = info

        # rooms (migrate if old format keyed by room name)
        raw_rooms = data.get("rooms", {})
        self.rooms = {}
        name_to_newid = {}

        # detect old: key is not 4 digits OR entry has no "name" and key is the name
        old_format_detected = any(not is_4digit(k) for k in raw_rooms.keys())

        def gen_room_id():
            while True:
                rid = str(random.randint(1000, 9999))
                if rid not in self.rooms:
                    return rid

        if old_format_detected:
            for old_key, info in raw_rooms.items():
                # old_key is room name
                name = info.get("owner") and old_key or info.get("name") or old_key
                rid = gen_room_id()
                name_to_newid[old_key] = rid
                members = set(info.get("members", []))
                msgs = info.get("messages", [])
                # fix messages 'to' to new id
                for m in msgs:
                    m["to"] = rid
                    m["target_type"] = "room"
                self.rooms[rid] = {
                    "id": rid,
                    "name": name,
                    "owner": info.get("owner"),
                    "members": members,
                    "messages": msgs,
                }
            # update users rooms set from names -> ids
            for u, info in self.users.items():
                new_set = set()
                for item in info["rooms"]:
                    new_set.add(name_to_newid.get(item, item if is_4digit(str(item)) else item))
                info["rooms"] = new_set
        else:
            # new format (keys are ids)
            for rid, info in raw_rooms.items():
                members = set(info.get("members", []))
                self.rooms[rid] = {
                    "id": rid,
                    "name": info.get("name") or rid,
                    "owner": info.get("owner"),
                    "members": members,
                    "messages": info.get("messages", []),
                }

        # dm messages
        self.dm_messages = {}
        for k, msgs in data.get("dm_messages", {}).items():
            a, b = k.split("|||")
            self.dm_messages[(a, b)] = msgs

    def save_data(self):
        try:
            data = {
                "users": {
                    u: {
                        "salt": info["salt"],
                        "pwd_hash": info["pwd_hash"],
                        "full_name": info.get("full_name", u),
                        "friends": list(info["friends"]),
                        "rooms": list(info["rooms"]),
                        "incoming": list(info["incoming"]),
                        "outgoing": list(info["outgoing"]),
                        "offline_queue": info.get("offline_queue", []),
                    } for u, info in self.users.items()
                },
                "rooms": {
                    rid: {
                        "name": info.get("name", rid),
                        "owner": info.get("owner"),
                        "members": list(info.get("members", set())),
                        "messages": info.get("messages", []),
                    } for rid, info in self.rooms.items()
                },
                "dm_messages": {
                    f"{k[0]}|||{k[1]}": v for k, v in self.dm_messages.items()
                }
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- helpers ----------
    def dm_key(self, a: str, b: str):
        return tuple(sorted([a, b]))

    def user_full_name(self, username: str) -> str:
        info = self.users.get(username)
        return (info.get("full_name") if info else None) or username

    def presence_update(self, username: str, online: bool):
        friends = self.users.get(username, {}).get("friends", set())
        payload = {"type": "presence", "user": username, "online": online, "ts": now_iso()}
        for u in list(friends):
            s = self.online.get(u)
            if s:
                json_send(s, payload)

    def emit_friend_list(self, username: str):
        info = self.users.get(username)
        if not info:
            return
        friends = [{
            "username": f,
            "full_name": self.user_full_name(f),
            "online": (f in self.online)
        } for f in sorted(info["friends"])]
        incoming = sorted(info["incoming"])
        outgoing = sorted(info["outgoing"])
        s = self.online.get(username)
        if s:
            json_send(s, {
                "type": "friend_list",
                "friends": friends,
                "incoming": incoming,
                "outgoing": outgoing,
                "ts": now_iso()
            })

    def emit_room_list(self, username: str):
        info = self.users.get(username)
        if not info:
            return
        rooms = []
        for rid in sorted(info["rooms"]):
            r = self.rooms.get(rid)
            if r:
                rooms.append({"id": rid, "name": r.get("name", rid)})
        s = self.online.get(username)
        if s:
            json_send(s, {"type": "room_list", "rooms": rooms, "ts": now_iso()})

    def deliver_or_queue(self, to_user: str, payload: Dict[str, Any]):
        s = self.online.get(to_user)
        if s:
            json_send(s, payload)
        else:
            uinfo = self.users.get(to_user)
            if uinfo is not None:
                uinfo.setdefault("offline_queue", []).append(payload)

    def gen_room_id(self) -> str:
        # 4-digit numeric id (1000-9999)
        while True:
            rid = str(random.randint(1000, 9999))
            if rid not in self.rooms:
                return rid

    # ---------- handlers ----------
    def handle_register(self, sock, p):
        u = (p.get("username") or "").strip()
        pw = p.get("password") or ""
        full_name = (p.get("full_name") or "").strip()
        if not u or not pw or not full_name:
            return {"type": "register", "ok": False, "error": "Thiếu họ tên / username / password"}
        with LOCK:
            if u in self.users:
                return {"type": "register", "ok": False, "error": "Username đã tồn tại"}
            salt = os.urandom(8).hex()
            self.users[u] = {
                "salt": salt,
                "pwd_hash": sha256(pw + salt),
                "full_name": full_name,
                "friends": set(),
                "rooms": set(),
                "incoming": set(),
                "outgoing": set(),
                "offline_queue": []
            }
            self.save_data()
        return {"type": "register", "ok": True, "message": "Đăng ký thành công"}

    def handle_login(self, sock, p):
        u = (p.get("username") or "").strip()
        pw = p.get("password") or ""
        with LOCK:
            info = self.users.get(u)
            if not info or sha256(pw + info["salt"]) != info["pwd_hash"]:
                return {"type": "login", "ok": False, "error": "Sai username hoặc password"}

            old = self.online.get(u)
            if old and old is not sock:
                try:
                    json_send(old, {"type": "system", "message": "Tài khoản đăng nhập ở nơi khác, ngắt kết nối.", "ts": now_iso()})
                    old.close()
                except Exception:
                    pass

            self.online[u] = sock
            self.sock2user[sock] = u

        json_send(sock, {"type": "login", "ok": True, "username": u, "ts": now_iso()})

        with LOCK:
            q = info.get("offline_queue", [])
            for item in q:
                json_send(sock, item)
            info["offline_queue"] = []
            self.save_data()

        self.emit_friend_list(u)
        self.emit_room_list(u)
        self.presence_update(u, True)
        return None

    def handle_logout(self, sock):
        with LOCK:
            u = self.sock2user.get(sock)
            if u:
                self.online.pop(u, None)
                self.sock2user.pop(sock, None)
        if u:
            self.presence_update(u, False)

    # --- SEARCH USERS (by login ID), return with full_name ---
    def handle_search_users(self, sock, p):
        q = (p.get("query") or "").lower()
        users = list(self.users.keys())
        if not q:
            res = [{"username": u, "full_name": self.user_full_name(u)} for u in sorted(users)[:50]]
            return {"type": "search_users", "ok": True, "results": res}
        exact  = [u for u in users if u.lower() == q]
        prefix = [u for u in users if u.lower().startswith(q) and u not in exact]
        substr = [u for u in users if q in u.lower() and u not in exact and u not in prefix]
        ordered = (exact + prefix + substr)[:50]
        res = [{"username": u, "full_name": self.user_full_name(u)} for u in ordered]
        return {"type": "search_users", "ok": True, "results": res}

    # --- FRIEND REQUESTS ---
    def handle_friend_request(self, sock, p):
        me = self.sock2user.get(sock)
        to_user = (p.get("to") or "").strip()
        if not me or not to_user or me == to_user:
            return {"type": "friend_request", "ok": False, "error": "Yêu cầu không hợp lệ"}
        with LOCK:
            if to_user not in self.users:
                return {"type": "friend_request", "ok": False, "error": "Người dùng không tồn tại"}
            info_me = self.users[me]
            info_to = self.users[to_user]
            if to_user in info_me["friends"]:
                return {"type": "friend_request", "ok": False, "error": "Đã là bạn"}
            if me in info_to["incoming"] or to_user in info_me["outgoing"]:
                pass
            else:
                info_me["outgoing"].add(to_user)
                info_to["incoming"].add(me)
                self.save_data()

        json_send(sock, {"type": "friend_request", "ok": True, "message": "Đã gửi lời mời", "ts": now_iso()})
        self.emit_friend_list(me)

        s = self.online.get(to_user)
        if s:
            json_send(s, {"type": "friend_request", "from": me, "ts": now_iso()})
            self.emit_friend_list(to_user)
        return None

    def handle_friend_accept(self, sock, p):
        me = self.sock2user.get(sock)
        from_user = (p.get("from") or "").strip()
        if not me or not from_user:
            return {"type": "friend_accept", "ok": False, "error": "Yêu cầu không hợp lệ"}
        with LOCK:
            info_me = self.users.get(me)
            info_fr = self.users.get(from_user)
            if not info_me or not info_fr:
                return {"type": "friend_accept", "ok": False, "error": "User không tồn tại"}
            if from_user in info_me["incoming"]:
                info_me["incoming"].discard(from_user)
                info_fr["outgoing"].discard(me)
                info_me["friends"].add(from_user)
                info_fr["friends"].add(me)
                self.save_data()
            else:
                return {"type": "friend_accept", "ok": False, "error": "Không có lời mời"}

        self.emit_friend_list(me)
        self.emit_friend_list(from_user)
        s_from = self.online.get(from_user)
        if s_from:
            json_send(s_from, {"type": "friend_accept", "from": me, "ok": True, "ts": now_iso()})
        return {"type": "friend_accept", "ok": True}

    def handle_friend_decline(self, sock, p):
        me = self.sock2user.get(sock)
        from_user = (p.get("from") or "").strip()
        with LOCK:
            info_me = self.users.get(me)
            info_fr = self.users.get(from_user)
            if info_me and info_fr and from_user in info_me["incoming"]:
                info_me["incoming"].discard(from_user)
                info_fr["outgoing"].discard(me)
                self.save_data()
        self.emit_friend_list(me)
        self.emit_friend_list(from_user)
        s_from = self.online.get(from_user)
        if s_from:
            json_send(s_from, {"type": "friend_decline", "from": me, "ok": True, "ts": now_iso()})
        return {"type": "friend_decline", "ok": True}

    # --- ROOMS / MESSAGES ---
    def handle_create_room(self, sock, p):
        me = self.sock2user.get(sock)
        room_name = (p.get("room_name") or "").strip()
        if not me or not room_name:
            return {"type": "create_room", "ok": False, "error": "Thiếu tên phòng"}
        with LOCK:
            rid = self.gen_room_id()
            self.rooms[rid] = {"id": rid, "name": room_name, "owner": me, "members": set([me]), "messages": []}
            self.users[me]["rooms"].add(rid)
            self.save_data()
        self.emit_room_list(me)
        return {"type": "create_room", "ok": True, "room": {"id": rid, "name": room_name}}

    def handle_join_room(self, sock, p):
        me = self.sock2user.get(sock)
        rid = str(p.get("room_id") or "").strip()
        with LOCK:
            info = self.rooms.get(rid)
            if not info:
                return {"type": "join_room", "ok": False, "error": "Phòng không tồn tại"}
            info["members"].add(me)
            self.users[me]["rooms"].add(rid)
            self.save_data()
        self.emit_room_list(me)
        # notify all members
        for u in list(info["members"]):
            s = self.online.get(u)
            if s:
                json_send(s, {"type": "room_update", "room_id": rid, "name": info["name"], "action": "join", "user": me, "ts": now_iso()})
        return {"type": "join_room", "ok": True, "room": {"id": rid, "name": info["name"]}}

    def handle_leave_room(self, sock, p):
        me = self.sock2user.get(sock)
        rid = str(p.get("room_id") or "").strip()
        with LOCK:
            info = self.rooms.get(rid)
            if not info:
                return {"type": "leave_room", "ok": False, "error": "Phòng không tồn tại"}
            if me not in info["members"]:
                return {"type": "leave_room", "ok": False, "error": "Bạn không ở trong phòng"}
            # remove member
            info["members"].discard(me)
            self.users[me]["rooms"].discard(rid)
            # decide deletion if empty
            deleted = False
            if len(info["members"]) == 0:
                deleted = True
                del self.rooms[rid]
            self.save_data()

        # notify remaining members or everyone who was in
        targets = list(info["members"]) if not deleted else list(set(list(info.get("members", set())) + [me]))
        for u in targets:
            s = self.online.get(u)
            if s:
                json_send(s, {"type": "room_update", "room_id": rid, "name": info.get("name"), "action": ("delete" if deleted else "leave"), "user": me, "ts": now_iso()})
        # ack to leaver
        return {"type": "leave_room", "ok": True}

    def handle_send_message(self, sock, p):
        me = self.sock2user.get(sock)
        target_type = p.get("target_type")
        to = str(p.get("to"))
        msgtype = p.get("msgtype", "text")
        content = p.get("content", "")
        filename = p.get("filename")
        data_b64 = p.get("data_base64")
        ts = now_iso()

        msg = {"from": me, "to": to, "target_type": target_type, "msgtype": msgtype,
               "content": content, "filename": filename, "data_base64": data_b64, "ts": ts}

        with LOCK:
            if target_type == "dm":
                if to not in self.users:
                    return {"type": "send_message", "ok": False, "error": "Người nhận không tồn tại"}
                key = self.dm_key(me, to)
                self.dm_messages.setdefault(key, []).append(msg)
                self.deliver_or_queue(to, {"type": "new_message", "message": msg, "ts": ts})
            elif target_type == "room":
                info = self.rooms.get(to)
                if not info or me not in info["members"]:
                    return {"type": "send_message", "ok": False, "error": "Không có quyền gửi vào phòng"}
                info["messages"].append(msg)
                for u in list(info["members"]):
                    s = self.online.get(u)
                    if s:
                        json_send(s, {"type": "new_message", "message": msg, "ts": ts})
            else:
                return {"type": "send_message", "ok": False, "error": "target_type không hợp lệ"}

            self.save_data()
        return {"type": "send_message", "ok": True, "ts": ts}

    def handle_fetch_history(self, sock, p):
        me = self.sock2user.get(sock)
        t = p.get("target_type"); to = str(p.get("to")); limit = int(p.get("limit", 200))
        with LOCK:
            if t == "dm":
                key = self.dm_key(me, to)
                msgs = self.dm_messages.get(key, [])[-limit:]
            else:
                info = self.rooms.get(to)
                if not info:
                    return {"type": "fetch_history", "ok": False, "error": "Phòng không tồn tại"}
                msgs = info.get("messages", [])[-limit:]
        return {"type": "fetch_history", "ok": True, "messages": msgs}

    def handle_typing(self, sock, p):
        me = self.sock2user.get(sock)
        t = p.get("target_type"); to = str(p.get("to")); is_typing = bool(p.get("is_typing"))
        if t == "dm":
            self.deliver_or_queue(to, {"type": "new_message", "message": {"from": me, "to": to, "target_type": "dm",
                                                                          "msgtype": "typing", "content": "", "filename": None,
                                                                          "data_base64": None, "ts": now_iso(),
                                                                          "is_typing": is_typing}, "ts": now_iso()})
        elif t == "room":
            with LOCK:
                info = self.rooms.get(to)
                if not info:
                    return {"type": "typing", "ok": False}
                for u in list(info["members"]):
                    s = self.online.get(u)
                    if s:
                        json_send(s, {"type": "typing", "from": me, "room_id": to, "is_typing": is_typing, "ts": now_iso()})
        return {"type": "typing", "ok": True}

    # ---------- client thread ----------
    def client_thread(self, sock: socket.socket, addr):
        fp = sock.makefile("r", encoding="utf-8", newline="\n")
        json_send(sock, {"type": "system", "ok": True, "message": "Kết nối server OK.", "ts": now_iso()})
        try:
            for obj in json_lines(fp):
                typ = obj.get("type"); p = obj.get("payload", {})
                if typ == "login":
                    self.handle_login(sock, p)
                elif typ == "friend_request":
                    self.handle_friend_request(sock, p)
                elif typ == "friend_accept":
                    json_send(sock, self.handle_friend_accept(sock, p))
                elif typ == "friend_decline":
                    json_send(sock, self.handle_friend_decline(sock, p))
                elif typ == "register":
                    json_send(sock, self.handle_register(sock, p))
                elif typ == "logout":
                    self.handle_logout(sock); json_send(sock, {"type": "logout", "ok": True})
                elif typ == "search_users":
                    json_send(sock, self.handle_search_users(sock, p))
                elif typ == "create_room":
                    json_send(sock, self.handle_create_room(sock, p))
                elif typ == "join_room":
                    json_send(sock, self.handle_join_room(sock, p))
                elif typ == "leave_room":
                    json_send(sock, self.handle_leave_room(sock, p))
                elif typ == "send_message":
                    json_send(sock, self.handle_send_message(sock, p))
                elif typ == "fetch_history":
                    json_send(sock, self.handle_fetch_history(sock, p))
                elif typ == "typing":
                    json_send(sock, self.handle_typing(sock, p))
                elif typ == "list_friends":
                    self.emit_friend_list(self.sock2user.get(sock, ""))
                elif typ == "list_rooms":
                    self.emit_room_list(self.sock2user.get(sock, ""))
                else:
                    json_send(sock, {"type": "system", "message": "Loại thông điệp không hỗ trợ.", "ts": now_iso()})
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
            self.handle_logout(sock)

    def run(self):
        print(f"Server listening on {self.host}:{self.port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            while True:
                c, addr = s.accept()
                threading.Thread(target=self.client_thread, args=(c, addr), daemon=True).start()

if __name__ == "__main__":
    ChatServer(HOST, PORT).run()
