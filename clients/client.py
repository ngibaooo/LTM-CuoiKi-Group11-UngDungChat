import socket
import threading
import json
import queue
import tkinter as tk
from contextlib import suppress
from tkinter import ttk, messagebox

HOST = "127.0.0.1"   # đổi thành IP của server nếu chạy khác máy
PORT = 5000

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Socket Chat — Client")
        self.root.geometry("980x640")

        # Networking
        self.sock = None
        self.receiver_thread = None
        self.running = False
        self._shutting_down = False

        # State
        self.user_id = None
        self.username = None
        self.current_room_id = None        # room đang chat nhóm
        self.current_dm_user_id = None     # user đang chat riêng (hiển thị trong khung phải)

        # Friends/presence/unread
        self.friends = []                  # [{id, display_name, status}]
        self.friend_map = {}               # id -> name
        self.presence = {}                 # id -> 'online'/'offline'
        self.unread = {}                   # id -> int (tin nhắn chưa đọc)

        # Local DM buffers: peer_id -> list[str] (dùng để render nhanh khi đổi người)
        self.dm_buffers = {}

        # UI holders
        self.login_frame = None
        self.main_frame = None

        # incoming queue (receiver thread -> UI thread)
        self.incoming = queue.Queue()

        # Build UI
        self._build_login_ui()

        # pump
        self.root.after(100, self._process_incoming)

    # ========================= UI BUILDERS =========================
    def _clear_root_children(self):
        for w in self.root.winfo_children():
            with suppress(Exception):
                w.destroy()

    def _build_login_ui(self):
        if self.main_frame is not None:
            with suppress(Exception):
                self.main_frame.destroy()
            self.main_frame = None

        self._clear_root_children()

        self.login_frame = ttk.Frame(self.root, padding=16)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(self.login_frame, text="Chào mừng 👋", font=("Segoe UI", 18, "bold"))
        title.pack(pady=(0, 12))

        self.auth_nb = ttk.Notebook(self.login_frame)
        self.auth_nb.pack(fill=tk.X, expand=False)

        # ---------- Tab Đăng nhập ----------
        tab_login = ttk.Frame(self.auth_nb, padding=10)
        self.auth_nb.add(tab_login, text="Đăng nhập")

        frm_l = ttk.Frame(tab_login); frm_l.pack()
        ttk.Label(frm_l, text="Username").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.lg_username = ttk.Entry(frm_l, width=32); self.lg_username.grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(frm_l, text="Password").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.lg_password = ttk.Entry(frm_l, show="*", width=32); self.lg_password.grid(row=1, column=1, padx=6, pady=6)

        btns_l = ttk.Frame(tab_login); btns_l.pack(pady=8)
        ttk.Button(btns_l, text="Đăng nhập", command=self.login).grid(row=0, column=1, padx=6)

        # ---------- Tab Đăng ký ----------
        tab_register = ttk.Frame(self.auth_nb, padding=10)
        self.auth_nb.add(tab_register, text="Đăng ký")

        frm_r = ttk.Frame(tab_register); frm_r.pack()
        ttk.Label(frm_r, text="Display name").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.reg_fullname = ttk.Entry(frm_r, width=32); self.reg_fullname.grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(frm_r, text="Username").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.reg_username = ttk.Entry(frm_r, width=32); self.reg_username.grid(row=1, column=1, padx=6, pady=6)

        ttk.Label(frm_r, text="Password").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.reg_password = ttk.Entry(frm_r, show="*", width=32); self.reg_password.grid(row=2, column=1, padx=6, pady=6)

        ttk.Label(frm_r, text="Email (required)").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        self.reg_email = ttk.Entry(frm_r, width=32); self.reg_email.grid(row=3, column=1, padx=6, pady=6)

        btns_r = ttk.Frame(tab_register); btns_r.pack(pady=8)
        ttk.Button(btns_r, text="Đăng ký", command=self.register).grid(row=0, column=1, padx=6)

    def _build_main_ui(self):
        if self.login_frame is not None:
            with suppress(Exception):
                self.login_frame.destroy()
            self.login_frame = None

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Navbar
        top = ttk.Frame(self.main_frame); top.pack(fill=tk.X)
        self.lbl_user = ttk.Label(top, text=f"Đang đăng nhập: {self.username} (id={self.user_id})")
        self.lbl_user.pack(side=tk.LEFT, padx=10, pady=6)

        ttk.Button(top, text="Đăng xuất", command=self.logout).pack(side=tk.RIGHT, padx=10)

        # Notebook
        self.nb = ttk.Notebook(self.main_frame)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- Tab: Chat ---
        self.tab_chat = ttk.Frame(self.nb)
        self.nb.add(self.tab_chat, text="Chat")

        left = ttk.Frame(self.tab_chat, padding=6); left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(self.tab_chat, padding=6); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Rooms
        ttk.Label(left, text="Phòng của tôi").pack(anchor="w")
        self.lst_rooms = tk.Listbox(left, height=10)
        self.lst_rooms.pack(fill=tk.Y, pady=4)
        self.lst_rooms.bind("<<ListboxSelect>>", self._on_select_room)

        frm_room_actions = ttk.Frame(left); frm_room_actions.pack(fill=tk.X, pady=6)
        ttk.Button(frm_room_actions, text="Tải phòng", command=self.show_chat_rooms).pack(side=tk.LEFT, padx=3)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Friends + presence + unread
        ttk.Label(left, text="Bạn bè").pack(anchor="w")
        self.lst_friends = tk.Listbox(left, height=14)
        self.lst_friends.pack(fill=tk.Y, pady=4)
        self.lst_friends.bind("<<ListboxSelect>>", self._on_select_friend)

        frm_friend_actions = ttk.Frame(left); frm_friend_actions.pack(fill=tk.X, pady=6)
        ttk.Button(frm_friend_actions, text="Tải bạn bè", command=self.show_friends).pack(side=tk.LEFT, padx=3)

        # Chat area (phải) dùng chung cho: Room hoặc DM (không mở cửa sổ/tab mới)
        header = ttk.Frame(right); header.pack(fill=tk.X)
        self.lbl_chat_target = ttk.Label(header, text="Chưa chọn phòng / người để chat")
        self.lbl_chat_target.pack(side=tk.LEFT)

        self.txt_chat = tk.Text(right, height=24, state=tk.DISABLED)
        self.txt_chat.pack(fill=tk.BOTH, expand=True, pady=6)

        entry = ttk.Frame(right); entry.pack(fill=tk.X)
        self.ent_message = ttk.Entry(entry); self.ent_message.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(entry, text="Gửi", command=self.send_message).pack(side=tk.LEFT, padx=6)

        # --- Tab: Phòng ---
        self.tab_rooms = ttk.Frame(self.nb)
        self.nb.add(self.tab_rooms, text="Phòng")

        frm_create = ttk.LabelFrame(self.tab_rooms, text="Tạo phòng")
        frm_create.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_create, text="Tên phòng").grid(row=0, column=0, padx=6, pady=6)
        self.ent_room_name = ttk.Entry(frm_create, width=32); self.ent_room_name.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_create, text="Tạo", command=self.create_chat_room).grid(row=0, column=2, padx=6, pady=6)

        frm_join = ttk.LabelFrame(self.tab_rooms, text="Tham gia phòng")
        frm_join.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_join, text="Tên phòng").grid(row=0, column=0, padx=6, pady=6)
        self.ent_join_room_id = ttk.Entry(frm_join, width=12); self.ent_join_room_id.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_join, text="Tham gia", command=self.join_chat_room).grid(row=0, column=2, padx=6, pady=6)

        # --- Tab: Bạn bè ---
        self.tab_friends = ttk.Frame(self.nb)
        self.nb.add(self.tab_friends, text="Bạn bè")

        frm_add = ttk.LabelFrame(self.tab_friends, text="Kết bạn")
        frm_add.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_add, text="Người nhận (Tên hiển thị)").grid(row=0, column=0, padx=6, pady=6)
        self.ent_add_friend_name = ttk.Entry(frm_add, width=20); self.ent_add_friend_name.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_add, text="Gửi yêu cầu", command=self.send_friend_request).grid(row=0, column=2, padx=6, pady=6)

        frm_accept = ttk.LabelFrame(self.tab_friends, text="Chấp nhận lời mời (nhập tên)")
        frm_accept.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_accept, text="Người gửi (Tên hiển thị)").grid(row=0, column=0, padx=6, pady=6)
        self.ent_accept_sender_name = ttk.Entry(frm_accept, width=20); self.ent_accept_sender_name.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_accept, text="Chấp nhận", command=self.accept_friend_request).grid(row=0, column=2, padx=6, pady=6)

        frm_pending = ttk.LabelFrame(self.tab_friends, text="Lời mời kết bạn đến")
        frm_pending.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.lst_friend_requests = tk.Listbox(frm_pending, height=8)
        self.lst_friend_requests.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        btns_pending = ttk.Frame(frm_pending); btns_pending.pack(pady=4)
        ttk.Button(btns_pending, text="Tải danh sách", command=self.show_friend_requests).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns_pending, text="Chấp nhận", command=self.accept_selected_request).pack(side=tk.LEFT, padx=4)

        # --- Tab: Tin nhắn ---
        self.tab_messages = ttk.Frame(self.nb)
        self.nb.add(self.tab_messages, text="Tin nhắn gần đây")

        ttk.Button(self.tab_messages, text="Tải tin nhắn của tôi", command=self.receive_messages).pack(pady=8)
        self.txt_messages = tk.Text(self.tab_messages, height=24, state=tk.DISABLED)
        self.txt_messages.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Load lists initially
        self.show_chat_rooms()
        self.show_friends()
        self.show_friend_requests()

        # Poll presence/unread dự phòng
        self.root.after(5000, self._poll_every_5s)

    # ========================= NETWORK =========================
    def connect_server(self):
        if self.sock:
            try:
                self.lbl_status.config(text=f"Đã kết nối tới {HOST}:{PORT}")
            except Exception:
                pass
            messagebox.showinfo("Thông báo", "Đã kết nối rồi")
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            if hasattr(self, "lbl_status"):
                self.lbl_status.config(text=f"Đã kết nối tới {HOST}:{PORT}")
        except Exception as e:
            self.sock = None
            messagebox.showerror("Lỗi", f"Không thể kết nối server: {e}")

    def _send(self, payload: dict):
        if not self.sock:
            messagebox.showwarning("Chưa kết nối", "Hãy kết nối tới server trước")
            return False
        try:
            self.sock.send(json.dumps(payload).encode())
            return True
        except Exception as e:
            if not self._shutting_down:
                messagebox.showerror("Lỗi", f"Mất kết nối server: {e}")
            return False

    def _start_receiver(self):
        if self.receiver_thread and self.receiver_thread.is_alive():
            return
        self.running = True
        self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
        self.receiver_thread.start()

    def _receiver_loop(self):
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    if not self._shutting_down:
                        self.incoming.put(("status", "Mất kết nối từ server"))
                    break

                text = data.decode(errors="ignore")
                try:
                    obj = json.loads(text)

                    if isinstance(obj, list):
                        self.incoming.put(("history", obj))

                    elif isinstance(obj, dict):
                        action = obj.get("action")
                        if action == "receive_message":
                            self.incoming.put(("chat", obj))
                        elif action in ("send_message_result", "send_private_result"):
                            self.incoming.put(("send_result", obj))
                        elif action == "presence_update":
                            self.incoming.put(("presence", obj))
                        elif action == "dm_history":
                            self.incoming.put(("dm_history", obj))
                        elif "chat_rooms" in obj:
                            self.incoming.put(("rooms", obj["chat_rooms"]))
                        elif "friends" in obj:
                            self.incoming.put(("friends", obj["friends"]))
                        elif "requests" in obj:
                            self.incoming.put(("friend_requests", obj["requests"]))
                        elif action == "friend_request":
                            self.incoming.put(("friend_request_notify", obj))
                        else:
                            self.incoming.put(("status", text))
                    else:
                        self.incoming.put(("status", text))

                except json.JSONDecodeError:
                    self.incoming.put(("status", text))

            except Exception as e:
                if not self._shutting_down:
                    self.incoming.put(("status", f"Lỗi nhận dữ liệu: {e}"))
                break

        self.running = False

    # ========================= AUTH =========================
    def register(self):
        if not self.sock:
            self.connect_server()
            if not self.sock:
                return
        full_name = self.reg_fullname.get().strip()
        username  = self.reg_username.get().strip()
        password  = self.reg_password.get().strip()
        email     = self.reg_email.get().strip()

        if not full_name:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập họ tên hiển thị")
            return
        if not username or not password or not email:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập đủ username, mật khẩu và email")
            return

        ok = self._send({
            "action": "register",
            "full_name": full_name,
            "username": username,
            "password": password,
            "email": email
        })
        if ok:
            try:
                resp = self.sock.recv(4096).decode()
                messagebox.showinfo("Phản hồi", resp)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không nhận được phản hồi: {e}")

    def login(self):
        if not self.sock:
            self.connect_server()
            if not self.sock:
                return
        username = self.lg_username.get().strip()
        password = self.lg_password.get().strip()
        if not username or not password:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập đủ username và password")
            return
        if not self._send({"action": "login", "username": username, "password": password}):
            return
        try:
            resp_raw = self.sock.recv(4096).decode()
            try:
                resp = json.loads(resp_raw)
            except json.JSONDecodeError:
                messagebox.showerror("Đăng nhập thất bại", f"Phản hồi không hợp lệ: {resp_raw}")
                return

            if resp.get("action") == "login_result" and resp.get("ok"):
                self.user_id = resp.get("user_id")
                self.username = resp.get("username") or username
                if not self.user_id:
                    messagebox.showerror("Lỗi", "Server không trả user_id")
                    return
                self._start_receiver()
                self._build_main_ui()
            else:
                err = resp.get("error", "unknown_error")
                if err == "invalid_credentials":
                    messagebox.showerror("Đăng nhập thất bại", "Sai username hoặc password")
                elif err == "db_connect_failed":
                    messagebox.showerror("Đăng nhập thất bại", "Không kết nối được Database trên server")
                else:
                    messagebox.showerror("Đăng nhập thất bại", f"Lỗi: {err}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không nhận được phản hồi: {e}")

    def logout(self):
        self._shutting_down = True
        try:
            with suppress(Exception):
                if self.sock:
                    self._send({"action": "logout"})
        finally:
            self.running = False
            if self.sock:
                with suppress(Exception): self.sock.shutdown(socket.SHUT_RDWR)
                with suppress(Exception): self.sock.close()
            self.sock = None

            # Dọn queue
            with suppress(queue.Empty):
                while True:
                    self.incoming.get_nowait()

            # Reset state
            self.user_id = None
            self.username = None
            self.current_room_id = None
            self.current_dm_user_id = None
            self.friends.clear(); self.friend_map.clear()
            self.presence.clear(); self.unread.clear(); self.dm_buffers.clear()

            self._build_login_ui()
            messagebox.showinfo("Đăng xuất", "Bạn đã đăng xuất.")
            self._shutting_down = False

    # ========================= CHAT (ROOM / DM trong khung phải) =========================
    def _on_select_room(self, _):
        sel = self.lst_rooms.curselection()
        if not sel: return
        item = self.lst_rooms.get(sel[0])
        try:
            room_id = int(item.split(" - ")[0])
        except Exception:
            room_id = None
        self.current_room_id = room_id
        self.current_dm_user_id = None
        self._render_room_header(item)
        self._clear_chat_area()

    def _on_select_friend(self, _):
        sel = self.lst_friends.curselection()
        if not sel: return
        item = self.lst_friends.get(sel[0])
        # Format: "<id> - <name> [ON/OFF] (n?)"
        try:
            uid = int(item.split(" - ")[0])
        except Exception:
            return
        self.current_dm_user_id = uid
        self.current_room_id = None
        # reset unread cho người này
        if uid in self.unread:
            self.unread[uid] = 0
            self._render_friend_list()
        # header
        name = self.friend_map.get(uid, f"User {uid}")
        sta = (self.presence.get(uid, "offline").lower() == "online")
        self.lbl_chat_target.config(text=f"Chat riêng với: {name} ({'ON' if sta else 'OFF'})")
        # hiển thị buffer nếu có, ngược lại xin server trả lịch sử
        self._clear_chat_area()
        if uid in self.dm_buffers:
            for line in self.dm_buffers[uid]:
                self._append_to_chat(line)
        else:
            self._send({"action": "get_dm_history", "user_id": self.user_id, "peer_id": uid})

    def _render_room_header(self, item_text):
        self.lbl_chat_target.config(text=f"Chat phòng: {item_text}")

    def _clear_chat_area(self):
        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.delete(1.0, tk.END)
        self.txt_chat.configure(state=tk.DISABLED)

    def _append_to_chat(self, text):
        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, text + "\n")
        self.txt_chat.see(tk.END)
        self.txt_chat.configure(state=tk.DISABLED)

    def send_message(self):
        if not self.user_id:
            messagebox.showwarning("Chưa đăng nhập", "Bạn chưa đăng nhập")
            return
        content = self.ent_message.get().strip()
        if not content:
            return

        # Group chat
        if self.current_room_id:
            ok = self._send({
                "action": "send_message",
                "sender_id": self.user_id,
                "content": content,
                "room_id": self.current_room_id
            })
            if ok:
                self._append_to_chat(f"[Tôi -> Room {self.current_room_id}]: {content}")
                self.ent_message.delete(0, tk.END)
            return

        # Private DM (trong cùng khung)
        if self.current_dm_user_id:
            peer = self.current_dm_user_id
            ok = self._send({
                "action": "send_private_message",
                "sender_id": self.user_id,
                "receiver_id": peer,
                "content": content
            })
            if ok:
                line = f"[Tôi -> {self.friend_map.get(peer, peer)}]: {content}"
                self._append_to_chat(line)
                self.dm_buffers.setdefault(peer, []).append(line)
                self.ent_message.delete(0, tk.END)
            return

        messagebox.showinfo("Chưa chọn mục tiêu", "Hãy chọn phòng hoặc một người bạn để chat")

    def receive_messages(self):
        if not self.user_id:
            return
        self._send({"action": "receive_message", "user_id": self.user_id})

    # ========================= ROOMS =========================
    def create_chat_room(self):
        name = self.ent_room_name.get().strip()
        if not name or not self.user_id:
            return
        self._send({"action": "create_chat_room", "room_name": name, "creator_id": self.user_id})

    def join_chat_room(self):
        room_name = self.ent_join_room_id.get().strip()
        if not room_name:
            messagebox.showwarning("Sai dữ liệu", "Tên phòng không được để trống")
            return
        self._send({"action": "join_chat_room", "room_name": room_name, "user_id": self.user_id})

    def show_chat_rooms(self):
        if not self.user_id:
            return
        self._send({"action": "show_chat_rooms", "user_id": self.user_id})

    # ========================= FRIENDS / REQUESTS =========================
    def send_friend_request(self):
        name_txt = self.ent_add_friend_name.get().strip()
        if not name_txt:
            messagebox.showwarning("Sai dữ liệu", "Tên hiển thị không được rỗng")
            return
        self._send({"action": "send_friend_request", "sender_id": self.user_id, "receiver_name": name_txt})

    def accept_friend_request(self):
        name_txt = self.ent_accept_sender_name.get().strip()
        if not name_txt:
            messagebox.showwarning("Sai dữ liệu", "Tên hiển thị không được rỗng")
            return
        self._send({"action": "accept_friend_request", "sender_name": name_txt, "receiver_id": self.user_id})

    def show_friend_requests(self):
        if not self.user_id: return
        self._send({"action": "show_friend_requests", "user_id": self.user_id})

    def accept_selected_request(self):
        sel = self.lst_friend_requests.curselection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một lời mời trong danh sách")
            return
        item = self.lst_friend_requests.get(sel[0])
        try:
            _uid, name = item.split(" - ", 1)
        except Exception:
            messagebox.showwarning("Lỗi", "Dữ liệu không hợp lệ")
            return
        self.ent_accept_sender_name.delete(0, tk.END)
        self.ent_accept_sender_name.insert(0, name)
        self.accept_friend_request()
        self.show_friend_requests()
        self.show_friends()

    def show_friends(self):
        if not self.user_id:
            return
        self._send({"action": "show_friends", "user_id": self.user_id})

    # ========================= RENDER LISTS =========================
    def _render_friend_list(self):
        self.lst_friends.delete(0, tk.END)
        for f in self.friends:
            fid = f["id"]
            name = f.get("display_name") or f.get("username") or f"id={fid}"
            status = (f.get("status") or self.presence.get(fid) or "offline").lower()
            sta = "[ON]" if status == "online" else "[OFF]"
            unread = self.unread.get(fid, 0)
            suffix = f" ({unread})" if unread > 0 else ""
            self.lst_friends.insert(tk.END, f"{fid} - {name} {sta}{suffix}")

    def _render_requests(self, reqs):
        self.lst_friend_requests.delete(0, tk.END)
        for r in reqs:
            self.lst_friend_requests.insert(tk.END, f"{r['id']} - {r['display_name']}")

    # ========================= INCOMING DISPATCH =========================
    def _process_incoming(self):
        try:
            while True:
                kind, payload = self.incoming.get_nowait()

                if kind == "status":
                    if not self._shutting_down:
                        messagebox.showinfo("Server", payload)

                elif kind == "chat":
                    # payload: {sender_id, receiver_id, content, sent_at, room_id?}
                    msg = payload
                    sender_id = msg.get("sender_id")
                    content = msg.get("content")
                    sent_at = msg.get("sent_at", "")
                    room_id = msg.get("room_id")

                    if room_id:
                        # group
                        if self.current_room_id == room_id:
                            self._append_to_chat(f"[{sent_at}] {sender_id} -> Room {room_id}: {content}")
                    else:
                        # DM
                        line = f"[{sent_at}] {sender_id}: {content}"
                        self.dm_buffers.setdefault(sender_id, []).append(line)
                        if self.current_dm_user_id == sender_id:
                            self._append_to_chat(line)
                        else:
                            self.unread[sender_id] = self.unread.get(sender_id, 0) + 1
                            self._render_friend_list()

                elif kind == "send_result":
                    msg = payload
                    if msg.get("ok"):
                        sent_at = msg.get("sent_at", "")
                        receiver_id = msg.get("receiver_id")
                        room_id = msg.get("room_id")
                        content = msg.get("content", "")
                        if room_id:
                            if self.current_room_id == room_id:
                                self._append_to_chat(f"[{sent_at}] Tôi -> Room {room_id}: {content}")
                        elif receiver_id:
                            line = f"[{sent_at}] Tôi -> {self.friend_map.get(receiver_id, receiver_id)}: {content}"
                            self.dm_buffers.setdefault(receiver_id, []).append(line)
                            if self.current_dm_user_id == receiver_id:
                                self._append_to_chat(line)

                elif kind == "rooms":
                    self.lst_rooms.delete(0, tk.END)
                    for room in payload:
                        self.lst_rooms.insert(tk.END, f"{room['room_id']} - {room['room_name']}")

                elif kind == "friends":
                    self.friends = payload or []
                    self.friend_map = {f["id"]: (f.get("display_name") or f.get("username") or f"id={f['id']}") for f in self.friends}
                    for f in self.friends:
                        self.presence[f["id"]] = (f.get("status") or "offline")
                        self.unread.setdefault(f["id"], 0)
                    self._render_friend_list()

                elif kind == "friend_requests":
                    self._render_requests(payload or [])

                elif kind == "friend_request_notify":
                    sender_name = payload.get("sender_name", "Ai đó")
                    messagebox.showinfo("Lời mời kết bạn", f"{sender_name} vừa gửi lời mời kết bạn cho bạn.")
                    self.show_friend_requests()

                elif kind == "history":
                    # tab "Tin nhắn gần đây"
                    self.txt_messages.configure(state=tk.NORMAL)
                    self.txt_messages.delete(1.0, tk.END)
                    for m in payload:
                        try:
                            sender_id = m[1]; receiver_id = m[2]; content = m[3]; sent_at = m[4]; room_id = m[5]
                        except Exception:
                            sender_id = m.get("sender_id"); receiver_id = m.get("receiver_id")
                            content = m.get("content"); sent_at = m.get("sent_at"); room_id = m.get("room_id")
                        self.txt_messages.insert(
                            tk.END,
                            f"[{sent_at}] {sender_id} -> {receiver_id or ('room '+str(room_id) if room_id else 'room')}: {content}\n"
                        )
                    self.txt_messages.configure(state=tk.DISABLED)

                elif kind == "presence":
                    uid = payload.get("user_id")
                    st = payload.get("status", "offline")
                    if uid:
                        self.presence[uid] = st
                        for f in self.friends:
                            if f["id"] == uid:
                                f["status"] = st
                                break
                        self._render_friend_list()

                elif kind == "dm_history":
                    peer = payload.get("peer_id")
                    msgs = payload.get("messages", [])
                    lines = []
                    for m in msgs:
                        s = m.get("sender_id"); r = m.get("receiver_id")
                        c = m.get("content"); t = m.get("sent_at")
                        if s == self.user_id:
                            lines.append(f"[{t}] Tôi -> {self.friend_map.get(peer, peer)}: {c}")
                        else:
                            lines.append(f"[{t}] {s}: {c}")
                    self.dm_buffers[peer] = lines
                    if self.current_dm_user_id == peer:
                        self._clear_chat_area()
                        for ln in lines:
                            self._append_to_chat(ln)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_incoming)

    # ========================= POLL =========================
    def _poll_every_5s(self):
        if self.user_id and self.sock:
            self.show_friends()
            self.show_friend_requests()
        self.root.after(5000, self._poll_every_5s)

# ---------------- Main ----------------
def main():
    root = tk.Tk()
    ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()
