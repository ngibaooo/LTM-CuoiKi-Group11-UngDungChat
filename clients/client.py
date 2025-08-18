#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client 1-file cho Ứng dụng Chat Socket (Python + Tkinter GUI)
-----------------------------------------------------------------
Tính năng triển khai (phía CLIENT):
- Đăng ký / Đăng nhập (qua socket TCP gửi JSON)
- Danh sách bạn bè (online/offline), tìm kiếm user, gửi/nhận lời mời kết bạn, chấp nhận/từ chối, xóa bạn
- Chat 1-1 và Chat nhóm (phòng): tạo phòng, mời bạn, tham gia, rời phòng
- Gửi/nhận tin nhắn dạng text + ảnh (base64). Hỗ trợ gửi file đính kèm dạng nhị phân (base64) ở mức cơ bản
- Thông báo (Notification) khi có tin nhắn mới ở tab nền (nháy dấu * và chuông của Tkinter)
- Trạng thái người dùng: online/offline, hiển thị trong Friend List
- Typing indicator (đang gõ) ở mỗi khung chat
- Tìm kiếm nội dung trong lịch sử chat theo từ khóa (cục bộ phía client)

LƯU Ý/ GIẢ ĐỊNH GIAO THỨC (CẦN SERVER PHÙ HỢP):
- Kết nối TCP tới server (host, port). Dữ liệu là các dòng JSON, mỗi thông điệp 1 dòng (\n-terminated)
- Mọi gói tin đều có khóa "type": "request" hoặc "event" hoặc "response"
- Gửi lên: {
    "type": "request",
    "req_id": int,         # client cấp số tăng dần
    "action": str,         # ví dụ: login, register, send_message, ...
    ... dữ liệu khác ...
  }
- Phản hồi: {
    "type": "response",
    "req_id": int,         # khớp với req_id
    "action": str,
    "ok": bool,
    "message": str,        # mô tả
    "data": {...}          # dữ liệu (nếu có)
  }
- Sự kiện đẩy từ server (không gắn req_id): {
    "type": "event",
    "event": str,          # ví dụ: message, presence_update, friend_request, room_update, ...
    "data": {...}
  }
- Một số action dự kiến phía client (server cần hỗ trợ tương ứng):
  register, login, get_friend_list, search_users, send_friend_request,
  respond_friend_request, remove_friend,
  create_room, join_room, leave_room, invite_to_room,
  send_message, typing
- Gói tin message (event)
  {
    "type": "event",
    "event": "message",
    "data": {
        "from": str,
        "to_type": "user"|"room",
        "to": str,                   # username hoặc room_id
        "msg_type": "text"|"image"|"file",
        "content": str,              # text hoặc base64
        "filename": str|None,        # nếu file/image
        "timestamp": int             # epoch seconds
    }
  }

CÀI ĐẶT PHỤ THUỘC:
- Python 3.8+
- Pillow (để hiển thị ảnh):
    pip install pillow

CHẠY:
    python client_app.py

Tác giả: GPT (kỹ sư lập trình mạng theo yêu cầu)
"""

import base64
import io
import json
import os
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter.scrolledtext import ScrolledText
except Exception as e:
    print("Lỗi import Tkinter:", e)
    sys.exit(1)

# Pillow để hiển thị ảnh
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ============================ Tiện ích ============================

def now_ts() -> int:
    return int(time.time())


def fmt_time(ts: Optional[int] = None) -> str:
    if ts is None:
        ts = now_ts()
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


# ============================ Lớp mạng: ChatClient ============================

class ChatClient:
    """Quản lý kết nối TCP tới server, gửi/nhận JSON theo dòng."""
    def __init__(self, on_event: Callable[[Dict[str, Any]], None]):
        self.on_event = on_event
        self.sock: Optional[socket.socket] = None
        self.reader_th: Optional[threading.Thread] = None
        self.writer_th: Optional[threading.Thread] = None
        self.send_q: "queue.Queue[str]" = queue.Queue()
        self.alive = threading.Event()
        self.alive.clear()
        self.req_id = 1
        self.lock = threading.Lock()
        self.buffer = b""

    def connect(self, host: str, port: int, timeout: float = 5.0) -> None:
        if self.sock:
            self.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.sock.settimeout(None)
        self.alive.set()
        self.reader_th = threading.Thread(target=self._reader_loop, daemon=True)
        self.writer_th = threading.Thread(target=self._writer_loop, daemon=True)
        self.reader_th.start()
        self.writer_th.start()

    def close(self):
        self.alive.clear()
        try:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.sock.close()
        except Exception:
            pass
        self.sock = None

    def next_req_id(self) -> int:
        with self.lock:
            rid = self.req_id
            self.req_id += 1
        return rid

    def send_json(self, obj: Dict[str, Any]):
        try:
            data = (json.dumps(obj, ensure_ascii=False) + "\n").encode('utf-8')
            self.send_q.put(data.decode('utf-8'))
        except Exception as e:
            print("send_json error:", e)

    def _writer_loop(self):
        try:
            while self.alive.is_set() and self.sock:
                try:
                    line = self.send_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if not self.sock:
                    break
                try:
                    self.sock.sendall(line.encode('utf-8'))
                except Exception as e:
                    print("Send error:", e)
                    break
        finally:
            self.alive.clear()

    def _reader_loop(self):
        buf = b""
        try:
            while self.alive.is_set() and self.sock:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode('utf-8'))
                        # Đẩy sang GUI thread qua callback
                        self.on_event(obj)
                    except Exception as e:
                        print("JSON parse error:", e, "line:", line[:200])
        except Exception as e:
            print("Reader loop error:", e)
        finally:
            self.alive.clear()
            # Thông báo ngắt kết nối
            try:
                self.on_event({"type": "event", "event": "disconnected", "data": {}})
            except Exception:
                pass


# ============================ Mô hình dữ liệu đơn giản ============================

@dataclass
class ChatMessage:
    sender: str
    to_type: str  # 'user' or 'room'
    to_id: str
    msg_type: str  # 'text' | 'image' | 'file'
    content: str
    filename: Optional[str] = None
    timestamp: int = field(default_factory=now_ts)


# ============================ GUI: Ứng dụng ============================

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat Socket Client")
        self.root.geometry("1200x750")

        # Hàng đợi nhận sự kiện từ mạng (đảm bảo thread-safe)
        self.ev_q: "queue.Queue[dict]" = queue.Queue()

        # Client mạng
        self.client = ChatClient(on_event=self._on_net_event)

        # Trạng thái người dùng đang đăng nhập
        self.me: Optional[str] = None
        self.token: Optional[str] = None  # nếu server trả về token

        # Bộ nhớ danh sách bạn và phòng
        self.friends: Dict[str, Dict[str, Any]] = {}  # username -> {online: bool}
        self.rooms: Dict[str, Dict[str, Any]] = {}    # room_id -> {name: str}
        self.friend_requests_inbox: List[str] = []    # danh sách user gửi lời mời đến mình

        # Bộ nhớ tin nhắn cục bộ: key = (to_type, to_id), value = List[ChatMessage]
        self.history: Dict[tuple, List[ChatMessage]] = {}

        # Map chat tab theo key
        self.chat_tabs: Dict[tuple, 'ChatTab'] = {}

        # Xây Login UI trước
        self._build_login_ui()

        # Poll hàng đợi sự kiện mạng mỗi 100ms
        self.root.after(100, self._process_events)

    # -------------------- Networking event entry (from network thread) --------------------
    def _on_net_event(self, obj: Dict[str, Any]):
        # Đưa vào hàng đợi để xử lý trên GUI thread
        self.ev_q.put(obj)

    def _process_events(self):
        try:
            while True:
                obj = self.ev_q.get_nowait()
                self._handle_event_on_gui(obj)
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    # -------------------- Build Login UI --------------------
    def _build_login_ui(self):
        self.login_frame = ttk.Frame(self.root, padding=20)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(self.login_frame, text="Đăng nhập / Đăng ký", font=("Segoe UI", 18, "bold"))
        title.pack(pady=(0, 15))

        grid = ttk.Frame(self.login_frame)
        grid.pack()

        ttk.Label(grid, text="Server Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.var_host = tk.StringVar(value="127.0.0.1")
        ttk.Entry(grid, textvariable=self.var_host, width=24).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(grid, text="Server Port:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.var_port = tk.StringVar(value="9009")
        ttk.Entry(grid, textvariable=self.var_port, width=10).grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(grid, text="Username:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.var_user = tk.StringVar()
        ttk.Entry(grid, textvariable=self.var_user, width=24).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(grid, text="Password:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        self.var_pass = tk.StringVar()
        ttk.Entry(grid, textvariable=self.var_pass, show="*", width=24).grid(row=1, column=3, padx=5, pady=5)

        btns = ttk.Frame(self.login_frame)
        btns.pack(pady=10)
        ttk.Button(btns, text="Kết nối", command=self._connect).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="Đăng nhập", command=self._login).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="Đăng ký", command=self._register).pack(side=tk.LEFT, padx=8)

        self.login_status = ttk.Label(self.login_frame, text="Chưa kết nối")
        self.login_status.pack(pady=5)

    def _connect(self):
        host = self.var_host.get().strip()
        try:
            port = int(self.var_port.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Port không hợp lệ")
            return
        try:
            self.client.connect(host, port)
            self.login_status.config(text=f"Đã kết nối tới {host}:{port}")
        except Exception as e:
            messagebox.showerror("Kết nối thất bại", str(e))

    def _register(self):
        if not self.client.sock:
            self._connect()
            if not self.client.sock:
                return
        username = self.var_user.get().strip()
        password = self.var_pass.get().strip()
        if not username or not password:
            messagebox.showwarning("Thiếu thông tin", "Nhập username và password")
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "register",
            "username": username,
            "password": password,
        })
        self.login_status.config(text="Đang đăng ký...")

    def _login(self):
        if not self.client.sock:
            self._connect()
            if not self.client.sock:
                return
        username = self.var_user.get().strip()
        password = self.var_pass.get().strip()
        if not username or not password:
            messagebox.showwarning("Thiếu thông tin", "Nhập username và password")
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "login",
            "username": username,
            "password": password,
        })
        self.login_status.config(text="Đang đăng nhập...")

    # -------------------- Build Main UI sau khi đăng nhập --------------------
    def _build_main_ui(self):
        self.login_frame.destroy()
        self.root.title(f"Chat Client - {self.me}")

        self.topbar = ttk.Frame(self.root)
        self.topbar.pack(fill=tk.X)
        ttk.Label(self.topbar, text=f"Xin chào, {self.me}", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=8, pady=6)
        self.btn_disconnect = ttk.Button(self.topbar, text="Ngắt kết nối", command=self._disconnect)
        self.btn_disconnect.pack(side=tk.RIGHT, padx=8)

        # Khung chính chia 2 cột
        self.main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.main.pack(fill=tk.BOTH, expand=True)

        # Cột trái: Danh bạ, lời mời, phòng
        self.left = ttk.Frame(self.main, padding=6)
        self.main.add(self.left, weight=1)

        # Cột phải: Tabs chat
        self.right = ttk.Frame(self.main, padding=6)
        self.main.add(self.right, weight=4)

        # ---- Friends section ----
        lab1 = ttk.Label(self.left, text="Danh bạ bạn bè", font=("Segoe UI", 11, "bold"))
        lab1.pack(anchor=tk.W)

        self.friend_tree = ttk.Treeview(self.left, columns=("status",), show='headings', height=10)
        self.friend_tree.heading("status", text="Bạn bè (Online/Offline)")
        self.friend_tree.pack(fill=tk.X, pady=4)
        self.friend_tree.bind('<Double-1>', self._on_friend_double_click)

        fr_btns = ttk.Frame(self.left)
        fr_btns.pack(fill=tk.X, pady=2)
        ttk.Button(fr_btns, text="Xóa bạn", command=self._remove_friend).pack(side=tk.LEFT, padx=2)

        # Tìm bạn + gửi lời mời
        ttk.Label(self.left, text="Tìm người dùng").pack(anchor=tk.W, pady=(8, 2))
        find_box = ttk.Frame(self.left)
        find_box.pack(fill=tk.X)
        self.var_search_user = tk.StringVar()
        ttk.Entry(find_box, textvariable=self.var_search_user).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(find_box, text="Tìm", command=self._search_users).pack(side=tk.LEFT, padx=4)

        self.search_result = ttk.Treeview(self.left, columns=("user",), show='headings', height=6)
        self.search_result.heading("user", text="Kết quả tìm kiếm")
        self.search_result.pack(fill=tk.X, pady=2)

        ttk.Button(self.left, text="Gửi lời mời kết bạn", command=self._send_friend_request).pack(anchor=tk.W, pady=2)

        # Lời mời kết bạn
        ttk.Label(self.left, text="Lời mời kết bạn đến", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(8,2))
        self.req_list = ttk.Treeview(self.left, columns=("from",), show='headings', height=5)
        self.req_list.heading("from", text="Từ người dùng")
        self.req_list.pack(fill=tk.X)

        req_btns = ttk.Frame(self.left)
        req_btns.pack(fill=tk.X, pady=2)
        ttk.Button(req_btns, text="Chấp nhận", command=lambda: self._respond_friend_request(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(req_btns, text="Từ chối", command=lambda: self._respond_friend_request(False)).pack(side=tk.LEFT, padx=2)

        # ---- Room section ----
        ttk.Label(self.left, text="Phòng chat", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(10,2))
        self.room_tree = ttk.Treeview(self.left, columns=("room",), show='headings', height=8)
        self.room_tree.heading("room", text="Danh sách phòng")
        self.room_tree.pack(fill=tk.X)
        self.room_tree.bind('<Double-1>', self._on_room_double_click)

        room_btns = ttk.Frame(self.left)
        room_btns.pack(fill=tk.X, pady=4)
        ttk.Button(room_btns, text="Tạo phòng", command=self._create_room_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(room_btns, text="Tham gia phòng", command=self._join_room_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(room_btns, text="Rời phòng", command=self._leave_selected_room).pack(side=tk.LEFT, padx=2)
        ttk.Button(room_btns, text="Mời vào phòng", command=self._invite_to_room_dialog).pack(side=tk.LEFT, padx=2)

        # ---- Right: Tabs chat ----
        self.tabs = ttk.Notebook(self.right)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        # Bottom bar: tìm kiếm toàn cục theo tab hiện tại
        bottom = ttk.Frame(self.right)
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, text="Tìm trong hội thoại hiện tại:").pack(side=tk.LEFT, padx=4)
        self.var_search_chat = tk.StringVar()
        e = ttk.Entry(bottom, textvariable=self.var_search_chat, width=30)
        e.pack(side=tk.LEFT)
        ttk.Button(bottom, text="Tìm", command=self._search_in_current_chat).pack(side=tk.LEFT, padx=4)

        # Tải danh bạ/ phòng lần đầu
        self._request_friend_list()

    # -------------------- Helper: mở tab chat --------------------
    def _open_chat_tab(self, to_type: str, to_id: str, title: Optional[str] = None):
        key = (to_type, to_id)
        if key in self.chat_tabs:
            tab = self.chat_tabs[key]
            self.tabs.select(tab.frame)
            return tab
        tab = ChatTab(self, to_type=to_type, to_id=to_id, title=title or f"{to_type}:{to_id}")
        self.chat_tabs[key] = tab
        self.tabs.add(tab.frame, text=tab.title)
        self.tabs.select(tab.frame)
        return tab

    # -------------------- Sự kiện UI --------------------
    def _disconnect(self):
        try:
            self.client.close()
        except Exception:
            pass
        messagebox.showinfo("Ngắt kết nối", "Đã ngắt kết nối khỏi server")

    def _on_friend_double_click(self, event):
        item = self.friend_tree.selection()
        if not item:
            return
        username = self.friend_tree.item(item[0], 'values')[0]
        self._open_chat_tab('user', username, title=f"👤 {username}")

    def _on_room_double_click(self, event):
        item = self.room_tree.selection()
        if not item:
            return
        room_id = self.room_tree.item(item[0], 'values')[0]
        room_name = self.rooms.get(room_id, {}).get('name', room_id)
        self._open_chat_tab('room', room_id, title=f"# {room_name}")

    def _remove_friend(self):
        item = self.friend_tree.selection()
        if not item:
            messagebox.showwarning("Chọn bạn", "Hãy chọn một người bạn để xóa")
            return
        username = self.friend_tree.item(item[0], 'values')[0]
        if messagebox.askyesno("Xác nhận", f"Xóa {username} khỏi danh sách bạn?"):
            rid = self.client.next_req_id()
            self.client.send_json({
                "type": "request",
                "req_id": rid,
                "action": "remove_friend",
                "username": username
            })

    def _search_users(self):
        q = self.var_search_user.get().strip()
        if not q:
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "search_users",
            "query": q
        })

    def _send_friend_request(self):
        sel = self.search_result.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một user trong kết quả tìm kiếm")
            return
        username = self.search_result.item(sel[0], 'values')[0]
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "send_friend_request",
            "to": username
        })
        messagebox.showinfo("Đã gửi", f"Đã gửi lời mời kết bạn tới {username}")

    def _respond_friend_request(self, accept: bool):
        sel = self.req_list.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Chọn một lời mời để phản hồi")
            return
        from_user = self.req_list.item(sel[0], 'values')[0]
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "respond_friend_request",
            "from": from_user,
            "accept": accept
        })
        # xóa khỏi UI ngay, server cũng sẽ gửi cập nhật danh bạ
        self.req_list.delete(sel[0])

    def _create_room_dialog(self):
        d = SimpleInputDialog(self.root, title="Tạo phòng", prompt="Tên phòng:") # type: ignore
        self.root.wait_window(d.top)
        name = d.value
        if not name:
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "create_room",
            "room_name": name
        })

    def _join_room_dialog(self):
        d = SimpleInputDialog(self.root, title="Tham gia phòng", prompt="Nhập Room ID:") # type: ignore
        self.root.wait_window(d.top)
        rid_str = d.value
        if not rid_str:
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "join_room",
            "room_id": rid_str
        })

    def _leave_selected_room(self):
        sel = self.room_tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Chọn một phòng để rời")
            return
        room_id = self.room_tree.item(sel[0], 'values')[0]
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "leave_room",
            "room_id": room_id
        })

    def _invite_to_room_dialog(self):
        sel = self.room_tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Chọn một phòng để mời")
            return
        room_id = self.room_tree.item(sel[0], 'values')[0]
        d = SimpleInputDialog(self.root, title="Mời vào phòng", prompt="Nhập username cần mời:") # type: ignore
        self.root.wait_window(d.top)
        username = d.value
        if not username:
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "invite_to_room",
            "room_id": room_id,
            "username": username
        })

    def _search_in_current_chat(self):
        key = self._current_tab_key()
        if not key:
            return
        tab = self.chat_tabs.get(key)
        if not tab:
            return
        kw = self.var_search_chat.get().strip()
        tab.search_keyword(kw)

    def _current_tab_key(self) -> Optional[tuple]:
        cur = self.tabs.select()
        for k, tab in self.chat_tabs.items():
            if str(tab.frame) == cur:
                return k
        return None

    def _request_friend_list(self):
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "get_friend_list",
        })

    # -------------------- Xử lý sự kiện mạng trên GUI thread --------------------
    def _handle_event_on_gui(self, obj: Dict[str, Any]):
        t = obj.get("type")
        if t == "response":
            action = obj.get("action")
            ok = obj.get("ok", False)
            data = obj.get("data") or {}
            msg = obj.get("message") or ""
            if action == "register":
                if ok:
                    self.login_status.config(text="Đăng ký thành công. Giờ hãy đăng nhập.")
                else:
                    messagebox.showerror("Đăng ký thất bại", msg)
            elif action == "login":
                if ok:
                    self.me = data.get("username") or self.var_user.get().strip()
                    self.token = data.get("token")
                    # data có thể chứa friends, rooms, requests...
                    self._build_main_ui()
                    self._apply_initial_payload(data)
                    messagebox.showinfo("Thành công", f"Đăng nhập thành công: {self.me}")
                else:
                    messagebox.showerror("Đăng nhập thất bại", msg)
                    self.login_status.config(text="Đăng nhập thất bại")
            elif action == "get_friend_list":
                if ok:
                    self._update_friend_list(data)
            elif action == "search_users":
                self._update_search_results(data if ok else {"users": []})
            elif action in ("send_friend_request", "respond_friend_request", "remove_friend"):
                # Server có thể đẩy cập nhật riêng, ở đây chỉ hiện thông báo
                if ok:
                    self._request_friend_list()
                else:
                    messagebox.showerror("Lỗi", obj.get("message") or action)
            elif action in ("create_room", "join_room", "leave_room", "invite_to_room"):
                if ok:
                    # refresh rooms nếu server trả về
                    self._update_rooms(data)
                    if action == "create_room":
                        rid = data.get("room_id")
                        name = data.get("room_name")
                        if rid:
                            self._open_chat_tab('room', str(rid), title=f"# {name or rid}")
                else:
                    messagebox.showerror("Lỗi phòng", obj.get("message") or action)
            elif action == "send_message":
                if not ok:
                    messagebox.showerror("Gửi thất bại", msg)
            elif action == "typing":
                # không hiện gì
                pass
            else:
                # các action khác
                if not ok:
                    print("Response lỗi:", action, msg)

        elif t == "event":
            ev = obj.get("event")
            data = obj.get("data") or {}
            if ev == "message":
                self._handle_incoming_message(data)
            elif ev == "presence_update":
                # data: {"username": str, "online": bool}
                u = data.get("username")
                onl = data.get("online")
                if u:
                    if u not in self.friends:
                        self.friends[u] = {"online": bool(onl)}
                    else:
                        self.friends[u]["online"] = bool(onl)
                    self._render_friend_tree()
            elif ev == "friend_request":
                from_user = data.get("from")
                if from_user:
                    self.friend_requests_inbox.append(from_user)
                    self._render_friend_requests()
                    self._notify(f"Lời mời kết bạn từ {from_user}")
            elif ev == "friend_update":
                # ví dụ server đẩy full friend list
                self._update_friend_list(data)
            elif ev == "room_update":
                # cập nhật danh sách phòng
                self._update_rooms(data)
            elif ev == "disconnected":
                messagebox.showwarning("Mất kết nối", "Đã mất kết nối tới server")
            else:
                # ignore
                pass

        else:
            # unknown
            pass

    # -------------------- Áp payload ban đầu sau login --------------------
    def _apply_initial_payload(self, data: Dict[str, Any]):
        # friends
        self._update_friend_list(data)
        # rooms
        self._update_rooms(data)
        # friend requests
        inbox = data.get("friend_requests_inbox") or []
        self.friend_requests_inbox = list(inbox)
        self._render_friend_requests()

    # -------------------- Friends --------------------
    def _update_friend_list(self, data: Dict[str, Any]):
        friends = data.get("friends") or []
        newmap = {}
        for f in friends:
            if isinstance(f, dict):
                username = f.get("username")
                online = f.get("online", False)
            else:
                username = str(f)
                online = False
            if not username:
                continue
            newmap[username] = {"online": bool(online)}
        self.friends = newmap
        self._render_friend_tree()

    def _render_friend_tree(self):
        for i in self.friend_tree.get_children():
            self.friend_tree.delete(i)
        # Sắp xếp online trước
        sorted_items = sorted(self.friends.items(), key=lambda kv: (not kv[1].get('online', False), kv[0].lower()))
        for u, info in sorted_items:
            status = "Online" if info.get('online') else "Offline"
            self.friend_tree.insert('', tk.END, values=(u,), tags=(status,))
        # style tags
        self.friend_tree.tag_configure('Online', background='#E8FFE8')
        self.friend_tree.tag_configure('Offline', background='#F8F8F8')

    def _update_search_results(self, data: Dict[str, Any]):
        users = data.get("users") or []
        for i in self.search_result.get_children():
            self.search_result.delete(i)
        for u in users:
            if isinstance(u, dict):
                uname = u.get("username")
            else:
                uname = str(u)
            if uname and uname != self.me:
                self.search_result.insert('', tk.END, values=(uname,))

    def _render_friend_requests(self):
        for i in self.req_list.get_children():
            self.req_list.delete(i)
        for u in self.friend_requests_inbox:
            self.req_list.insert('', tk.END, values=(u,))

    # -------------------- Rooms --------------------
    def _update_rooms(self, data: Dict[str, Any]):
        rooms = data.get("rooms") or []
        newmap = {}
        for r in rooms:
            if isinstance(r, dict):
                rid = str(r.get("room_id"))
                name = r.get("room_name") or rid
            else:
                rid = str(r)
                name = rid
            newmap[rid] = {"name": name}
        self.rooms = newmap
        self._render_room_tree()

    def _render_room_tree(self):
        for i in self.room_tree.get_children():
            self.room_tree.delete(i)
        # Sắp xếp theo tên
        sorted_items = sorted(self.rooms.items(), key=lambda kv: kv[1].get('name','').lower())
        for rid, info in sorted_items:
            self.room_tree.insert('', tk.END, values=(rid,))

    # -------------------- Xử lý tin nhắn đến --------------------
    def _handle_incoming_message(self, data: Dict[str, Any]):
        from_user = data.get("from") or "?"
        to_type = data.get("to_type") or "user"
        to_id = str(data.get("to"))
        msg_type = data.get("msg_type") or "text"
        content = data.get("content") or ""
        filename = data.get("filename")
        ts = int(data.get("timestamp") or now_ts())

        # Xác định hội thoại (key)
        key = None
        if to_type == 'user':
            # nếu tin nhắn gửi tới mình từ ai đó -> key là hội thoại với người đó
            if to_id == self.me:
                key = ('user', from_user)
            # nếu tin do mình gửi, server có thể echo lại -> key là người nhận
            elif from_user == self.me:
                key = ('user', to_id)
            else:
                # fallback
                key = ('user', from_user)
        else:
            key = ('room', to_id)

        # Lưu lịch sử
        msg = ChatMessage(sender=from_user, to_type=key[0], to_id=key[1], msg_type=msg_type, content=content, filename=filename, timestamp=ts)
        self.history.setdefault(key, []).append(msg)

        # Mở tab nếu chưa có
        if key not in self.chat_tabs:
            title = f"👤 {key[1]}" if key[0] == 'user' else f"# {self.rooms.get(key[1],{}).get('name', key[1])}"
            tab = self._open_chat_tab(key[0], key[1], title=title)
        else:
            tab = self.chat_tabs[key]

        # Render
        tab.append_message(msg)

        # Nếu tab không phải tab hiện tại -> gắn dấu * thông báo và kêu chuông
        current = self._current_tab_key()
        if current != key:
            self._set_tab_badge(tab, True)
            self._notify("Tin nhắn mới")

    def _set_tab_badge(self, tab: 'ChatTab', badged: bool):
        # Đổi tiêu đề tab: thêm * khi có tin mới
        idx = self.tabs.index(tab.frame)
        title = tab.title
        if badged and not title.endswith(" *"):
            title += " *"
        if (not badged) and title.endswith(" *"):
            title = title[:-2]
        tab.title = title
        self.tabs.tab(idx, text=title)

    def _notify(self, text: str):
        try:
            self.root.bell()
        except Exception:
            pass

    # -------------------- Gửi tin nhắn/typing từ ChatTab --------------------
    def send_text(self, to_type: str, to_id: str, text: str):
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "send_message",
            "to_type": to_type,
            "to": to_id,
            "msg_type": "text",
            "content": text
        })

    def send_image(self, to_type: str, to_id: str, filepath: str):
        try:
            with open(filepath, 'rb') as f:
                b = f.read()
            b64 = base64.b64encode(b).decode('ascii')
            filename = os.path.basename(filepath)
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "send_message",
            "to_type": to_type,
            "to": to_id,
            "msg_type": "image",
            "content": b64,
            "filename": filename
        })

    def send_file(self, to_type: str, to_id: str, filepath: str):
        try:
            with open(filepath, 'rb') as f:
                b = f.read()
            b64 = base64.b64encode(b).decode('ascii')
            filename = os.path.basename(filepath)
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))
            return
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "send_message",
            "to_type": to_type,
            "to": to_id,
            "msg_type": "file",
            "content": b64,
            "filename": filename
        })

    def send_typing(self, to_type: str, to_id: str, is_typing: bool):
        rid = self.client.next_req_id()
        self.client.send_json({
            "type": "request",
            "req_id": rid,
            "action": "typing",
            "to_type": to_type,
            "to": to_id,
            "is_typing": bool(is_typing)
        })

    # -------------------- Main loop --------------------
    def run(self):
        self.root.mainloop()


# ============================ ChatTab ============================

class ChatTab:
    def __init__(self, app: ChatGUI, to_type: str, to_id: str, title: str):
        self.app = app
        self.to_type = to_type
        self.to_id = to_id
        self.title = title
        self.frame = ttk.Frame(app.tabs)

        # Danh sách PhotoImage giữ tham chiếu để ảnh không bị GC
        self._images: List[Any] = []

        # Lịch sử local cho tab này
        self.key = (to_type, to_id)
        self.history = app.history.setdefault(self.key, [])

        # UI
        self._build_ui()

        # typing throttle
        self._last_type_send = 0.0

    def _build_ui(self):
        topbar = ttk.Frame(self.frame)
        topbar.pack(fill=tk.X)
        self.typing_label = ttk.Label(topbar, text="")
        self.typing_label.pack(side=tk.LEFT, padx=4)

        self.text = ScrolledText(self.frame, wrap=tk.WORD, state=tk.DISABLED, height=25)
        self.text.pack(fill=tk.BOTH, expand=True, pady=4)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=tk.X)

        self.var_input = tk.StringVar()
        entry = ttk.Entry(bottom, textvariable=self.var_input)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        entry.bind('<Return>', lambda e: self._send_text())
        entry.bind('<KeyPress>', self._on_keypress)

        ttk.Button(bottom, text="Gửi", command=self._send_text).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="Ảnh", command=self._pick_image).pack(side=tk.LEFT)
        ttk.Button(bottom, text="File", command=self._pick_file).pack(side=tk.LEFT, padx=2)

        # Load lịch sử sẵn có (nếu có)
        for m in self.history:
            self.append_message(m, skip_store=True)

        # clear badge khi mở
        self.app._set_tab_badge(self, False)

    def _on_keypress(self, event):
        now = time.time()
        if now - self._last_type_send > 1.0:
            self.app.send_typing(self.to_type, self.to_id, True)
            self._last_type_send = now
        # ẩn label typing sau 2s nếu không có update
        self.frame.after(2000, lambda: self.typing_label.config(text=""))

    def _send_text(self):
        text = self.var_input.get().strip()
        if not text:
            return
        self.app.send_text(self.to_type, self.to_id, text)
        # hiển thị ngay ở local
        msg = ChatMessage(sender=self.app.me or "me", to_type=self.to_type, to_id=self.to_id, msg_type='text', content=text, timestamp=now_ts())
        self.history.append(msg)
        self.append_message(msg, skip_store=True)
        self.var_input.set("")

    def _pick_image(self):
        fp = filedialog.askopenfilename(title="Chọn ảnh", filetypes=[("Ảnh", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("Tất cả", "*.*")])
        if not fp:
            return
        self.app.send_image(self.to_type, self.to_id, fp)
        # hiển thị local ngay
        try:
            with open(fp, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
            msg = ChatMessage(sender=self.app.me or "me", to_type=self.to_type, to_id=self.to_id, msg_type='image', content=b64, filename=os.path.basename(fp), timestamp=now_ts())
            self.history.append(msg)
            self.append_message(msg, skip_store=True)
        except Exception as e:
            messagebox.showerror("Lỗi ảnh", str(e))

    def _pick_file(self):
        fp = filedialog.askopenfilename(title="Chọn file")
        if not fp:
            return
        self.app.send_file(self.to_type, self.to_id, fp)
        # hiển thị local
        try:
            with open(fp, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
            msg = ChatMessage(sender=self.app.me or "me", to_type=self.to_type, to_id=self.to_id, msg_type='file', content=b64, filename=os.path.basename(fp), timestamp=now_ts())
            self.history.append(msg)
            self.append_message(msg, skip_store=True)
        except Exception as e:
            messagebox.showerror("Lỗi file", str(e))

    def append_message(self, m: ChatMessage, skip_store: bool=False):
        if not skip_store:
            self.history.append(m)
        self.text.configure(state=tk.NORMAL)
        ts = fmt_time(m.timestamp)
        if m.msg_type == 'text':
            prefix = f"[{ts}] {m.sender}: "
            self.text.insert(tk.END, prefix + m.content + "\n")
        elif m.msg_type == 'image':
            # In dòng mô tả
            line = f"[{ts}] {m.sender} gửi ảnh: {m.filename or ''}\n"
            self.text.insert(tk.END, line)
            # Hiển thị ảnh nếu có PIL
            try:
                imgdata = base64.b64decode(m.content)
                if PIL_AVAILABLE:
                    im = Image.open(io.BytesIO(imgdata))
                    im.thumbnail((480, 480))
                    tkimg = ImageTk.PhotoImage(im)
                else:
                    # Thử với PhotoImage nếu là PNG/GIF
                    tkimg = tk.PhotoImage(data=base64.b64encode(imgdata))
                self._images.append(tkimg)  # giữ tham chiếu
                self.text.image_create(tk.END, image=tkimg)
                self.text.insert(tk.END, "\n")
            except Exception as e:
                self.text.insert(tk.END, f"(Không thể hiển thị ảnh: {e})\n")
        else:  # file
            line = f"[{ts}] {m.sender} gửi file: {m.filename or 'file.bin'} (đính kèm {len(m.content)} base64)\n"
            self.text.insert(tk.END, line)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)
        # clear badge nếu tab hiện tại
        cur = self.app._current_tab_key()
        if cur == self.key:
            self.app._set_tab_badge(self, False)