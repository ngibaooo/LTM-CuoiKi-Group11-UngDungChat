import socket
import threading
import json
import queue
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

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

        # State
        self.user_id = None
        self.username = None
        self.current_room_id = None  # room đang chat nhóm
        self.current_dm_user_id = None  # user đang chat riêng

        # A queue for messages from receiver thread
        self.incoming = queue.Queue()

        # Build UI
        self._build_login_ui()

        # Periodically process incoming messages
        self.root.after(100, self._process_incoming)

    # ========================= UI BUILDERS =========================
    def _build_login_ui(self):
        self.login_frame = ttk.Frame(self.root, padding=16)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(self.login_frame, text="Đăng nhập / Đăng ký", font=("Segoe UI", 18, "bold"))
        title.pack(pady=(0, 12))

        form = ttk.Frame(self.login_frame)
        form.pack()

        ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.ent_username = ttk.Entry(form, width=32)
        self.ent_username.grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(form, text="Password").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.ent_password = ttk.Entry(form, show="*", width=32)
        self.ent_password.grid(row=1, column=1, padx=6, pady=6)

        ttk.Label(form, text="Email (khi đăng ký)").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.ent_email = ttk.Entry(form, width=32)
        self.ent_email.grid(row=2, column=1, padx=6, pady=6)

        buttons = ttk.Frame(self.login_frame)
        buttons.pack(pady=8)

        self.btn_connect = ttk.Button(buttons, text="Kết nối", command=self.connect_server)
        self.btn_connect.grid(row=0, column=0, padx=6)

        self.btn_login = ttk.Button(buttons, text="Đăng nhập", command=self.login)
        self.btn_login.grid(row=0, column=1, padx=6)

        self.btn_register = ttk.Button(buttons, text="Đăng ký", command=self.register)
        self.btn_register.grid(row=0, column=2, padx=6)

        self.lbl_status = ttk.Label(self.login_frame, text="Chưa kết nối")
        self.lbl_status.pack(pady=(8, 0))

    def _build_main_ui(self):
        # Destroy login
        for w in self.login_frame.winfo_children():
            w.destroy()
        self.login_frame.destroy()

        # Navbar
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X)
        self.lbl_user = ttk.Label(top, text=f"Đang đăng nhập: {self.username} (id={self.user_id})")
        self.lbl_user.pack(side=tk.LEFT, padx=10, pady=6)

        ttk.Button(top, text="Đăng xuất", command=self.logout).pack(side=tk.RIGHT, padx=10)

        # Notebook
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- Tab: Chat ---
        self.tab_chat = ttk.Frame(self.nb)
        self.nb.add(self.tab_chat, text="Chat")

        left = ttk.Frame(self.tab_chat, padding=6)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(self.tab_chat, padding=6)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Rooms list
        ttk.Label(left, text="Phòng của tôi").pack(anchor="w")
        self.lst_rooms = tk.Listbox(left, height=14)
        self.lst_rooms.pack(fill=tk.Y, pady=4)
        self.lst_rooms.bind("<<ListboxSelect>>", self._on_select_room)

        frm_room_actions = ttk.Frame(left)
        frm_room_actions.pack(fill=tk.X, pady=6)
        ttk.Button(frm_room_actions, text="Tải phòng", command=self.show_chat_rooms).pack(side=tk.LEFT, padx=3)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Friends list
        ttk.Label(left, text="Bạn bè").pack(anchor="w")
        self.lst_friends = tk.Listbox(left, height=10)
        self.lst_friends.pack(fill=tk.Y, pady=4)
        self.lst_friends.bind("<<ListboxSelect>>", self._on_select_friend)

        frm_friend_actions = ttk.Frame(left)
        frm_friend_actions.pack(fill=tk.X, pady=6)
        ttk.Button(frm_friend_actions, text="Tải bạn bè", command=self.show_friends).pack(side=tk.LEFT, padx=3)

        # Chat area
        header = ttk.Frame(right)
        header.pack(fill=tk.X)
        self.lbl_chat_target = ttk.Label(header, text="Chưa chọn phòng / người để chat")
        self.lbl_chat_target.pack(side=tk.LEFT)

        self.txt_chat = tk.Text(right, height=24, state=tk.DISABLED)
        self.txt_chat.pack(fill=tk.BOTH, expand=True, pady=6)

        entry = ttk.Frame(right)
        entry.pack(fill=tk.X)
        self.ent_message = ttk.Entry(entry)
        self.ent_message.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(entry, text="Gửi", command=self.send_message).pack(side=tk.LEFT, padx=6)

        # --- Tab: Phòng ---
        self.tab_rooms = ttk.Frame(self.nb)
        self.nb.add(self.tab_rooms, text="Phòng")

        frm_create = ttk.LabelFrame(self.tab_rooms, text="Tạo phòng")
        frm_create.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_create, text="Tên phòng").grid(row=0, column=0, padx=6, pady=6)
        self.ent_room_name = ttk.Entry(frm_create, width=32)
        self.ent_room_name.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_create, text="Tạo", command=self.create_chat_room).grid(row=0, column=2, padx=6, pady=6)

        frm_join = ttk.LabelFrame(self.tab_rooms, text="Tham gia phòng")
        frm_join.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_join, text="Room ID").grid(row=0, column=0, padx=6, pady=6)
        self.ent_join_room_id = ttk.Entry(frm_join, width=12)
        self.ent_join_room_id.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_join, text="Tham gia", command=self.join_chat_room).grid(row=0, column=2, padx=6, pady=6)

        # --- Tab: Bạn bè ---
        self.tab_friends = ttk.Frame(self.nb)
        self.nb.add(self.tab_friends, text="Bạn bè")

        frm_add = ttk.LabelFrame(self.tab_friends, text="Kết bạn")
        frm_add.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_add, text="Người nhận (user_id)").grid(row=0, column=0, padx=6, pady=6)
        self.ent_add_friend_id = ttk.Entry(frm_add, width=12)
        self.ent_add_friend_id.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_add, text="Gửi yêu cầu", command=self.send_friend_request).grid(row=0, column=2, padx=6, pady=6)

        frm_accept = ttk.LabelFrame(self.tab_friends, text="Chấp nhận lời mời")
        frm_accept.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(frm_accept, text="Người gửi (user_id)").grid(row=0, column=0, padx=6, pady=6)
        self.ent_accept_sender_id = ttk.Entry(frm_accept, width=12)
        self.ent_accept_sender_id.grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(frm_accept, text="Chấp nhận", command=self.accept_friend_request).grid(row=0, column=2, padx=6, pady=6)

        # --- Tab: Tin nhắn ---
        self.tab_messages = ttk.Frame(self.nb)
        self.nb.add(self.tab_messages, text="Tin nhắn gần đây")

        ttk.Button(self.tab_messages, text="Tải tin nhắn của tôi", command=self.receive_messages).pack(pady=8)
        self.txt_messages = tk.Text(self.tab_messages, height=24, state=tk.DISABLED)
        self.txt_messages.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Load lists initially
        self.show_chat_rooms()
        self.show_friends()

    # ========================= NETWORK =========================
    def connect_server(self):
        if self.sock:
            messagebox.showinfo("Thông báo", "Đã kết nối rồi")
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self.lbl_status.config(text=f"Đã kết nối tới {HOST}:{PORT}")
        except Exception as e:
            self.sock = None
            messagebox.showerror("Lỗi", f"Không thể kết nối server: {e}")

    def _send(self, payload: dict):
        if not self.sock:
            messagebox.showwarning("Chưa kết nối", "Hãy Kết nối tới server trước")
            return False
        try:
            self.sock.send(json.dumps(payload).encode())
            return True
        except Exception as e:
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
                    self.incoming.put(("status", "Mất kết nối từ server"))
                    break
                text = data.decode(errors="ignore")

                # Try parse JSON
                try:
                    obj = json.loads(text)
                    # Detect different payload shapes
                    if isinstance(obj, dict) and obj.get("action") == "receive_message":
                        self.incoming.put(("chat", obj.get("message")))
                    elif isinstance(obj, dict) and "chat_rooms" in obj:
                        self.incoming.put(("rooms", obj["chat_rooms"]))
                    elif isinstance(obj, dict) and "friends" in obj:
                        self.incoming.put(("friends", obj["friends"]))
                    elif isinstance(obj, list):
                        self.incoming.put(("history", obj))
                    else:
                        # Fallback show raw
                        self.incoming.put(("status", text))
                except json.JSONDecodeError:
                    # plain string response
                    self.incoming.put(("status", text))
            except Exception as e:
                self.incoming.put(("status", f"Lỗi nhận dữ liệu: {e}"))
                break
        self.running = False

    # ========================= AUTH =========================
    def register(self):
        if not self.sock:
            self.connect_server()
            if not self.sock:
                return
        username = self.ent_username.get().strip()
        password = self.ent_password.get().strip()
        email = self.ent_email.get().strip()
        if not username or not password or not email:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập đủ username, password, email")
            return
        ok = self._send({
            "action": "register",
            "username": username,
            "password": password,
            "email": email
        })
        if ok:
            # read one immediate response synchronously (before starting receiver)
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
        username = self.ent_username.get().strip()
        password = self.ent_password.get().strip()
        if not username or not password:
            messagebox.showwarning("Thiếu dữ liệu", "Nhập đủ username và password")
            return
        ok = self._send({
            "action": "login",
            "username": username,
            "password": password
        })
        if not ok:
            return
        # Nhận phản hồi dạng JSON từ server
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
        if not self.sock:
            return
        self._send({"action": "logout"})
        # Đóng ngay phía client
        try:
            self.running = False
            if self.sock:
                self.sock.close()
            self.sock = None
        finally:
            messagebox.showinfo("Đăng xuất", "Đã ngắt kết nối")
            self.root.destroy()

    # ========================= CHAT =========================
    def _on_select_room(self, _):
        sel = self.lst_rooms.curselection()
        if not sel:
            return
        idx = sel[0]
        item = self.lst_rooms.get(idx)
        # Expect format: "<room_id> - <room_name>"
        try:
            room_id = int(item.split(" - ")[0])
        except Exception:
            room_id = None
        self.current_room_id = room_id
        self.current_dm_user_id = None
        self.lbl_chat_target.config(text=f"Chat phòng: {item}")

    def _on_select_friend(self, _):
        sel = self.lst_friends.curselection()
        if not sel:
            return
        idx = sel[0]
        item = self.lst_friends.get(idx)
        # Expect format: "<user_id> - <username>"
        try:
            uid = int(item.split(" - ")[0])
        except Exception:
            uid = None
        self.current_dm_user_id = uid
        self.current_room_id = None
        self.lbl_chat_target.config(text=f"Chat riêng với: {item}")

    def _append_chat(self, text):
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

        # Group chat via room_id — this matches your current server implementation
        if self.current_room_id:
            ok = self._send({
                "action": "send_message",
                "sender_id": self.user_id,
                "content": content,
                "room_id": self.current_room_id
            })
            if ok:
                self._append_chat(f"[Tôi -> Room {self.current_room_id}]: {content}")
                self.ent_message.delete(0, tk.END)
            return

        # Private chat — requires a small server-side addition (see ghi chú bên dưới)
        if self.current_dm_user_id:
            ok = self._send({
                "action": "send_private_message",  # ⚠️ cần bổ sung handler ở server
                "sender_id": self.user_id,
                "receiver_id": self.current_dm_user_id,
                "content": content
            })
            if ok:
                self._append_chat(f"[Tôi -> User {self.current_dm_user_id}]: {content}")
                self.ent_message.delete(0, tk.END)
            return

        messagebox.showinfo("Chưa chọn mục tiêu", "Hãy chọn phòng hoặc một người bạn để chat")

    def receive_messages(self):
        if not self.user_id:
            return
        self._send({
            "action": "receive_message",  # theo server: 'receive_message' để server trả lịch sử messages liên quan
            "user_id": self.user_id
        })

    # ========================= ROOMS =========================
    def create_chat_room(self):
        name = self.ent_room_name.get().strip()
        if not name:
            return
        if not self.user_id:
            return
        self._send({
            "action": "create_chat_room",
            "room_name": name,
            "creator_id": self.user_id
        })

    def join_chat_room(self):
        rid_txt = self.ent_join_room_id.get().strip()
        if not rid_txt or not rid_txt.isdigit():
            messagebox.showwarning("Sai dữ liệu", "Room ID phải là số")
            return
        rid = int(rid_txt)
        self._send({
            "action": "join_chat_room",
            "room_id": rid,
            "user_id": self.user_id
        })

    def show_chat_rooms(self):
        if not self.user_id:
            return
        self._send({
            "action": "show_chat_rooms",
            "user_id": self.user_id
        })

    # ========================= FRIENDS =========================
    def send_friend_request(self):
        rid_txt = self.ent_add_friend_id.get().strip()
        if not rid_txt or not rid_txt.isdigit():
            messagebox.showwarning("Sai dữ liệu", "user_id phải là số")
            return
        rid = int(rid_txt)
        self._send({
            "action": "send_friend_request",
            "sender_id": self.user_id,
            "receiver_id": rid
        })

    def accept_friend_request(self):
        sid_txt = self.ent_accept_sender_id.get().strip()
        if not sid_txt or not sid_txt.isdigit():
            messagebox.showwarning("Sai dữ liệu", "user_id phải là số")
            return
        sid = int(sid_txt)
        self._send({
            "action": "accept_friend_request",
            "sender_id": sid,
            "receiver_id": self.user_id
        })

    def show_friends(self):
        if not self.user_id:
            return
        self._send({
            "action": "show_friends",
            "user_id": self.user_id
        })

    # ========================= DISPATCH INCOMING =========================
    def _process_incoming(self):
        try:
            while True:
                kind, payload = self.incoming.get_nowait()
                if kind == "status":
                    # show status in messages tab footer
                    messagebox.showinfo("Server", payload)
                elif kind == "chat":
                    self._append_chat(f"[Phòng/Hệ thống]: {payload}")
                elif kind == "rooms":
                    self.lst_rooms.delete(0, tk.END)
                    for room in payload:  # {room_id, room_name}
                        self.lst_rooms.insert(tk.END, f"{room['room_id']} - {room['room_name']}")
                elif kind == "friends":
                    self.lst_friends.delete(0, tk.END)
                    for f in payload:  # {id, username}
                        self.lst_friends.insert(tk.END, f"{f['id']} - {f['username']}")
                elif kind == "history":
                    self.txt_messages.configure(state=tk.NORMAL)
                    self.txt_messages.delete(1.0, tk.END)
                    for m in payload:
                        # server message tuple mapping assumed: [id, sender_id, receiver_id, content, send_at, room_id]
                        try:
                            sender_id = m[1]
                            receiver_id = m[2]
                            content = m[3]
                            send_at = m[4]
                        except Exception:
                            sender_id = m.get('sender_id')
                            receiver_id = m.get('receiver_id')
                            content = m.get('content')
                            send_at = m.get('send_at')
                        self.txt_messages.insert(tk.END, f"[{send_at}] {sender_id} -> {receiver_id or 'room'}: {content}\n")
                    self.txt_messages.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_incoming)


def main():
    root = tk.Tk()
    ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()


# test