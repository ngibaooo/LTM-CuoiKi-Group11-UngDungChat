#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import threading
import json
import os
import hashlib
import base64
import datetime
from typing import Dict, Any, List, Set, Tuple

HOST = "127.0.0.1"
PORT = 5555
DATA_FILE = "server_data.json"
LOCK = threading.RLock()

def now_iso():
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
        if line:
            try:
                yield json.loads(line)
            except Exception:
                continue

class ChatServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        # Persistent state
        self.users: Dict[str, Dict[str, Any]] = {}  # username -> {salt, pwd_hash, friends:set, rooms:set, incoming:set, outgoing:set, offline_queue:list}
        self.rooms: Dict[str, Dict[str, Any]] = {}  # room -> {owner:str, members:set, messages:list}
        self.dm_messages: Dict[Tuple[str,str], List[Dict[str,Any]]] = {}  # (u1,u2) sorted -> list of messages
        # Runtime state
        self.online: Dict[str, socket.socket] = {}  # username -> socket
        self.sock2user: Dict[socket.socket, str] = {}

        self.load_data()

    # ---------- Persistence ----------
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.users = {}
                for u, info in data.get("users", {}).items():
                    info["friends"] = set(info.get("friends", []))
                    info["rooms"] = set(info.get("rooms", []))
                    info["incoming"] = set(info.get("incoming", []))
                    info["outgoing"] = set(info.get("outgoing", []))
                    self.users[u] = info
                self.rooms = {}
                for r, info in data.get("rooms", {}).items():
                    info["members"] = set(info.get("members", []))
                    self.rooms[r] = info
                self.dm_messages = {}
                for k, msgs in data.get("dm_messages", {}).items():
                    u1, u2 = k.split("|||")
                    self.dm_messages[(u1,u2)] = msgs
            except Exception:
                pass

    def save_data(self):
        try:
            data = {
                "users": {
                    u: {
                        "salt": info["salt"],
                        "pwd_hash": info["pwd_hash"],
                        "friends": list(info["friends"]),
                        "rooms": list(info["rooms"]),
                        "incoming": list(info["incoming"]),
                        "outgoing": list(info["outgoing"]),
                        "offline_queue": info.get("offline_queue", []),
                    } for u, info in self.users.items()
                },
                "rooms": {
                    r: {
                        "owner": info["owner"],
                        "members": list(info["members"]),
                        "messages": info.get("messages", []),
                    } for r, info in self.rooms.items()
                },
                "dm_messages": {
                    f"{k[0]}|||{k[1]}": v for k, v in self.dm_messages.items()
                }
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- Helpers ----------
    def send_system(self, sock, text):
        json_send(sock, {"type": "system", "ok": True, "message": text, "ts": now_iso()})

    def broadcast_to(self, usernames: Set[str], payload: Dict[str, Any], exclude: str=None):
        for u in list(usernames):
            s = self.online.get(u)
            if s and (exclude is None or u != exclude):
                json_send(s, payload)

    def presence_update(self, username: str, online: bool):
        friends = self.users.get(username, {}).get("friends", set())
        payload = {"type":"presence","user":username,"online":online,"ts":now_iso()}
        self.broadcast_to(friends, payload, exclude=username)

    def emit_friend_list(self, username: str):
        info = self.users.get(username)
        if not info: return
        friends = []
        for f in sorted(info["friends"]):
            friends.append({"username": f, "online": (f in self.online)})
        incoming = sorted(info["incoming"])
        outgoing = sorted(info["outgoing"])
        s = self.online.get(username)
        if s:
            json_send(s, {"type":"friend_list","friends":friends,"incoming":incoming,"outgoing":outgoing,"ts":now_iso()})

    def list_my_rooms(self, username: str):
        info = self.users.get(username)
        if not info: return []
        rooms = sorted(list(info["rooms"]))
        s = self.online.get(username)
        if s:
            json_send(s, {"type":"room_list","rooms":rooms,"ts":now_iso()})
        return rooms

    def dm_key(self, a: str, b: str):
        return tuple(sorted([a,b]))

    def deliver_or_queue(self, to_user: str, message_obj: Dict[str,Any]):
        s = self.online.get(to_user)
        if s:
            json_send(s, {"type":"new_message","message":message_obj,"ts":now_iso()})
        else:
            uinfo = self.users.get(to_user)
            if uinfo is not None:
                uinfo.setdefault("offline_queue", []).append({"type":"new_message","message":message_obj,"ts":now_iso()})

    # ---------- Handlers ----------
    def handle_register(self, sock, payload):
        username = payload.get("username","").strip()
        password = payload.get("password","")
        if not username or not password:
            return {"type":"register","ok":False,"error":"Thiếu username/password"}
        with LOCK:
            if username in self.users:
                return {"type":"register","ok":False,"error":"Username đã tồn tại"}
            salt = os.urandom(8).hex()
            pwd_hash = sha256(password + salt)
            self.users[username] = {
                "salt": salt,
                "pwd_hash": pwd_hash,
                "friends": set(),
                "rooms": set(),
                "incoming": set(),
                "outgoing": set(),
                "offline_queue": []
            }
            self.save_data()
        return {"type":"register","ok":True,"message":"Đăng ký thành công"}

    def handle_login(self, sock, payload):
        username = payload.get("username","").strip()
        password = payload.get("password","")
        with LOCK:
            info = self.users.get(username)
            if not info:
                return {"type":"login","ok":False,"error":"Sai username hoặc password"}
            if sha256(password + info["salt"]) != info["pwd_hash"]:
                return {"type":"login","ok":False,"error":"Sai username hoặc password"}

            # terminate old session if any
            old = self.online.get(username)
            if old and old is not sock:
                try:
                    json_send(old, {"type":"system","message":"Tài khoản đăng nhập ở nơi khác, ngắt kết nối.","ts":now_iso()})
                    old.close()
                except Exception:
                    pass

            self.online[username] = sock
            self.sock2user[sock] = username

        # ack
        resp = {"type":"login","ok":True,"username":username,"ts":now_iso()}
        # send offline queue
        with LOCK:
            queue = info.get("offline_queue", [])
            for item in queue:
                json_send(sock, item)
            info["offline_queue"] = []
            self.save_data()

        self.emit_friend_list(username)
        self.list_my_rooms(username)
        self.presence_update(username, True)
        return resp

    def handle_logout(self, sock):
        with LOCK:
            username = self.sock2user.get(sock)
            if username:
                self.online.pop(username, None)
                self.sock2user.pop(sock, None)
        if username:
            self.presence_update(username, False)

    def handle_search_users(self, sock, payload):
        q = (payload.get("query","") or "").lower()
        res = []
        with LOCK:
            for u in self.users.keys():
                if q in u.lower():
                    res.append(u)
        return {"type":"search_users","ok":True,"results":sorted(res)[:50]}

    # ---- Friend management ----
    def handle_friend_request(self, sock, payload):
        me = self.sock2user.get(sock)
        to_user = payload.get("to")
        if not me or not to_user or me == to_user:
            return {"type":"friend_request","ok":False,"error":"Yêu cầu không hợp lệ"}
        with LOCK:
            if to_user not in self.users:
                return {"type":"friend_request","ok":False,"error":"Người dùng không tồn tại"}
            info_me = self.users[me]
            info_to = self.users[to_user]
            if to_user in info_me["friends"]:
                return {"type":"friend_request","ok":False,"error":"Đã là bạn"}
            info_me["outgoing"].add(to_user)
            info_to["incoming"].add(me)
            self.save_data()
        # notify
        self.emit_friend_list(me)
        s = self.online.get(to_user)
        if s:
            json_send(s, {"type":"friend_request","from":me,"ts":now_iso()})
            self.emit_friend_list(to_user)
        return {"type":"friend_request","ok":True,"message":"Đã gửi lời mời"}

    def handle_friend_accept(self, sock, payload):
        me = self.sock2user.get(sock)
        from_user = payload.get("from")
        if not me or not from_user:
            return {"type":"friend_accept","ok":False,"error":"Yêu cầu không hợp lệ"}
        with LOCK:
            info_me = self.users.get(me)
            info_from = self.users.get(from_user)
            if not info_me or not info_from: 
                return {"type":"friend_accept","ok":False,"error":"User không tồn tại"}
            if from_user in info_me["incoming"]:
                info_me["incoming"].discard(from_user)
                info_from["outgoing"].discard(me)
                info_me["friends"].add(from_user)
                info_from["friends"].add(me)
                self.save_data()
            else:
                return {"type":"friend_accept","ok":False,"error":"Không có lời mời"}
        self.emit_friend_list(me)
        self.emit_friend_list(from_user)
        return {"type":"friend_accept","ok":True}

    def handle_friend_decline(self, sock, payload):
        me = self.sock2user.get(sock)
        from_user = payload.get("from")
        with LOCK:
            info_me = self.users.get(me)
            info_from = self.users.get(from_user)
            if info_me and info_from and from_user in info_me["incoming"]:
                info_me["incoming"].discard(from_user)
                info_from["outgoing"].discard(me)
                self.save_data()
        self.emit_friend_list(me)
        self.emit_friend_list(from_user)
        return {"type":"friend_decline","ok":True}

    def handle_friend_remove(self, sock, payload):
        me = self.sock2user.get(sock)
        who = payload.get("who")
        with LOCK:
            info_me = self.users.get(me)
            info_w = self.users.get(who)
            if info_me and info_w:
                info_me["friends"].discard(who)
                info_w["friends"].discard(me)
                self.save_data()
        self.emit_friend_list(me)
        self.emit_friend_list(who)
        return {"type":"friend_remove","ok":True}

    # ---- Rooms ----
    def handle_create_room(self, sock, payload):
        me = self.sock2user.get(sock)
        room = payload.get("room","").strip()
        if not room:
            return {"type":"create_room","ok":False,"error":"Thiếu tên phòng"}
        with LOCK:
            if room in self.rooms:
                return {"type":"create_room","ok":False,"error":"Phòng đã tồn tại"}
            self.rooms[room] = {"owner": me, "members": set([me]), "messages":[]}
            self.users[me]["rooms"].add(room)
            self.save_data()
        self.list_my_rooms(me)
        return {"type":"create_room","ok":True,"room":room}

    def handle_join_room(self, sock, payload):
        me = self.sock2user.get(sock)
        room = payload.get("room","").strip()
        with LOCK:
            info = self.rooms.get(room)
            if not info:
                return {"type":"join_room","ok":False,"error":"Phòng không tồn tại"}
            info["members"].add(me)
            self.users[me]["rooms"].add(room)
            self.save_data()
        self.list_my_rooms(me)
        # notify members
        self.broadcast_to(set(info["members"]), {"type":"room_update","room":room,"action":"join","user":me,"ts":now_iso()}, exclude=None)
        return {"type":"join_room","ok":True,"room":room}

    def handle_leave_room(self, sock, payload):
        me = self.sock2user.get(sock)
        room = payload.get("room","").strip()
        with LOCK:
            info = self.rooms.get(room)
            if not info: 
                return {"type":"leave_room","ok":False,"error":"Phòng không tồn tại"}
            info["members"].discard(me)
            self.users[me]["rooms"].discard(room)
            self.save_data()
        self.list_my_rooms(me)
        self.broadcast_to(set(info["members"]), {"type":"room_update","room":room,"action":"leave","user":me,"ts":now_iso()}, exclude=None)
        return {"type":"leave_room","ok":True}

    # ---- Messaging & typing ----
    def handle_send_message(self, sock, payload):
        me = self.sock2user.get(sock)
        target_type = payload.get("target_type")  # 'dm' or 'room'
        to = payload.get("to")
        msgtype = payload.get("msgtype","text")
        content = payload.get("content","")
        filename = payload.get("filename")
        data_b64 = payload.get("data_base64")
        ts = now_iso()

        msg = {
            "from": me, "to": to, "target_type": target_type,
            "msgtype": msgtype, "content": content, "filename": filename,
            "data_base64": data_b64, "ts": ts
        }

        with LOCK:
            if target_type == "dm":
                if to not in self.users:
                    return {"type":"send_message","ok":False,"error":"Người nhận không tồn tại"}
                key = self.dm_key(me, to)
                self.dm_messages.setdefault(key, []).append(msg)
                # deliver
                self.deliver_or_queue(to, msg)
            elif target_type == "room":
                info = self.rooms.get(to)
                if not info or me not in info["members"]:
                    return {"type":"send_message","ok":False,"error":"Không có quyền gửi vào phòng"}
                info["messages"].append(msg)
                members = set(info["members"])
                self.broadcast_to(members, {"type":"new_message","message":msg,"ts":ts}, exclude=None)
            else:
                return {"type":"send_message","ok":False,"error":"target_type không hợp lệ"}

            self.save_data()
        return {"type":"send_message","ok":True,"ts":ts}

    def handle_fetch_history(self, sock, payload):
        me = self.sock2user.get(sock)
        target_type = payload.get("target_type")
        to = payload.get("to")
        limit = int(payload.get("limit", 200))
        with LOCK:
            if target_type == "dm":
                key = self.dm_key(me, to)
                msgs = self.dm_messages.get(key, [])[-limit:]
            else:
                info = self.rooms.get(to)
                if not info:
                    return {"type":"fetch_history","ok":False,"error":"Phòng không tồn tại"}
                msgs = info.get("messages", [])[-limit:]
        return {"type":"fetch_history","ok":True,"messages":msgs}

    def handle_search_history(self, sock, payload):
        me = self.sock2user.get(sock)
        target_type = payload.get("target_type")
        to = payload.get("to")
        keyword = (payload.get("keyword","") or "").lower()
        date_from = payload.get("date_from")  # 'YYYY-MM-DD'
        date_to = payload.get("date_to")
        def in_range(ts):
            try:
                d = datetime.datetime.strptime(ts[:10], "%Y-%m-%d").date()
            except Exception:
                return True
            ok = True
            if date_from:
                ok &= d >= datetime.datetime.strptime(date_from,"%Y-%m-%d").date()
            if date_to:
                ok &= d <= datetime.datetime.strptime(date_to,"%Y-%m-%d").date()
            return ok

        with LOCK:
            if target_type == "dm":
                key = self.dm_key(me, to)
                msgs = self.dm_messages.get(key, [])
            else:
                info = self.rooms.get(to)
                if not info:
                    return {"type":"search_history","ok":False,"error":"Phòng không tồn tại"}
                msgs = info.get("messages", [])
            results = []
            for m in msgs:
                text = (m.get("content") or "").lower()
                if (not keyword or keyword in text) and in_range(m.get("ts","")):
                    results.append(m)
        return {"type":"search_history","ok":True,"messages":results[-500:]}

    def handle_typing(self, sock, payload):
        me = self.sock2user.get(sock)
        target_type = payload.get("target_type")
        to = payload.get("to")
        is_typing = bool(payload.get("is_typing"))
        if target_type == "dm":
            self.deliver_or_queue(to, {"from":me,"to":to,"target_type":"dm","msgtype":"typing","content":"","filename":None,"data_base64":None,"ts":now_iso(),"is_typing":is_typing})
        elif target_type == "room":
            with LOCK:
                info = self.rooms.get(to)
                if not info: return {"type":"typing","ok":False}
                self.broadcast_to(set(info["members"]), {"type":"typing","from":me,"room":to,"is_typing":is_typing,"ts":now_iso()}, exclude=None)
        return {"type":"typing","ok":True}

    # ---------- Client thread ----------
    def client_thread(self, sock: socket.socket, addr):
        fp = sock.makefile("r", encoding="utf-8", newline="\n")
        self.send_system(sock, "Kết nối server OK.")
        try:
            for obj in json_lines(fp):
                t = obj.get("type")
                payload = obj.get("payload", {})
                if t == "register":
                    json_send(sock, self.handle_register(sock, payload))
                elif t == "login":
                    json_send(sock, self.handle_login(sock, payload))
                elif t == "logout":
                    self.handle_logout(sock)
                    json_send(sock, {"type":"logout","ok":True})
                elif t == "search_users":
                    json_send(sock, self.handle_search_users(sock, payload))
                elif t == "friend_request":
                    json_send(sock, self.handle_friend_request(sock, payload))
                elif t == "friend_accept":
                    json_send(sock, self.handle_friend_accept(sock, payload))
                elif t == "friend_decline":
                    json_send(sock, self.handle_friend_decline(sock, payload))
                elif t == "friend_remove":
                    json_send(sock, self.handle_friend_remove(sock, payload))
                elif t == "create_room":
                    json_send(sock, self.handle_create_room(sock, payload))
                elif t == "join_room":
                    json_send(sock, self.handle_join_room(sock, payload))
                elif t == "leave_room":
                    json_send(sock, self.handle_leave_room(sock, payload))
                elif t == "send_message":
                    json_send(sock, self.handle_send_message(sock, payload))
                elif t == "fetch_history":
                    json_send(sock, self.handle_fetch_history(sock, payload))
                elif t == "search_history":
                    json_send(sock, self.handle_search_history(sock, payload))
                elif t == "typing":
                    json_send(sock, self.handle_typing(sock, payload))
                elif t == "list_friends":
                    self.emit_friend_list(self.sock2user.get(sock,""))
                elif t == "list_rooms":
                    self.list_my_rooms(self.sock2user.get(sock,""))
                else:
                    self.send_system(sock, "Loại thông điệp không hỗ trợ.")
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
            self.handle_logout(sock)

    # ---------- Run ----------
    def run(self):
        print(f"Server listening on {self.host}:{self.port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            while True:
                client, addr = s.accept()
                t = threading.Thread(target=self.client_thread, args=(client, addr), daemon=True)
                t.start()

if __name__ == "__main__":
    ChatServer(HOST, PORT).run()
