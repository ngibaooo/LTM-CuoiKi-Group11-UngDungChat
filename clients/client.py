#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import threading
import json
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import base64
import os
import datetime

HOST = "127.0.0.1"
PORT = 5555

# ------------- Networking layer -------------
class NetClient:
    def __init__(self, host, port, on_event):
        self.host = host
        self.port = port
        self.sock = None
        self.fp = None
        self.rx_thread = None
        self.on_event = on_event
        self.lock = threading.RLock()
        self.connected = False

    def connect(self):
        if self.connected:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.fp = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self.connected = True
        self.rx_thread = threading.Thread(target=self.rx_loop, daemon=True)
        self.rx_thread.start()

    def close(self):
        try:
            with self.lock:
                if self.sock:
                    self.sock.close()
        except Exception:
            pass
        self.connected = False

    def send(self, typ, payload):
        if not self.connected:
            self.connect()
        obj = {"type": typ, "payload": payload}
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            self.sock.sendall(data)

    def rx_loop(self):
        try:
            for line in self.fp:
                line = line.strip()
                if not line: 
                    continue
                try:
                    obj = json.loads(line)
                    self.on_event(obj)
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            self.connected = False
            self.on_event({"type":"system","message":"Mất kết nối server."})

# ------------- GUI & App state -------------
class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Socket Chat Client")
        self.geometry("1000x640")
        self.minsize(900, 560)

        self.net = NetClient(HOST, PORT, self.enqueue_event)
        self.event_q = queue.Queue()

        # State
        self.username = None
        self.current_chat = None  # ("dm", username) or ("room", roomname)
        self.friends = {}         # name -> online(bool)
        self.incoming = []        # pending requests
        self.outgoing = []
        self.rooms = []           # room list
        self.unread = {}          # chat_id -> count
        self.history = {}         # chat_id -> list of messages
        self.images_cache = []    # keep references to PhotoImage
        self.typing_labels = {}   # chat_id -> label text (who typing)
        self.main_ui_built = False

        # UI
        self.build_login_ui()
        self.after(100, self.process_events)

    # ---------- Utilities ----------
    def chat_id(self, kind, name):
        return f"{kind}:{name}"

    def enqueue_event(self, obj):
        self.event_q.put(obj)

    def process_events(self):
        while not self.event_q.empty():
            obj = self.event_q.get()
            self.handle_event(obj)
        self.after(100, self.process_events)

    def safe_bell(self):
        try:
            self.bell()
        except Exception:
            pass

    # ---------- Login/Register UI ----------
    def build_login_ui(self):
        self.login_frame = ttk.Frame(self)
        self.login_frame.pack(fill="both", expand=True, padx=16, pady=16)

        title = ttk.Label(self.login_frame, text="ỨNG DỤNG CHAT SOCKET", font=("Segoe UI", 18, "bold"))
        title.pack(pady=10)

        nb = ttk.Notebook(self.login_frame)
        self.tab_login = ttk.Frame(nb)
        self.tab_register = ttk.Frame(nb)
        nb.add(self.tab_login, text="Đăng nhập")
        nb.add(self.tab_register, text="Đăng ký")
        nb.pack(fill="x", pady=10)

        # Login
        self.l_user = tk.StringVar()
        self.l_pass = tk.StringVar()
        ttk.Label(self.tab_login, text="Username").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ent_user = ttk.Entry(self.tab_login, textvariable=self.l_user, width=30)
        ent_user.grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(self.tab_login, text="Password").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ent_pass = ttk.Entry(self.tab_login, textvariable=self.l_pass, show="•", width=30)
        ent_pass.grid(row=1, column=1, padx=6, pady=6)
        btn_login = ttk.Button(self.tab_login, text="Đăng nhập", command=self.do_login)
        btn_login.grid(row=2, column=0, columnspan=2, pady=10)

        # Enter to login
        ent_user.bind("<Return>", lambda e: self.do_login())
        ent_pass.bind("<Return>", lambda e: self.do_login())

        # Register
        self.r_user = tk.StringVar()
        self.r_pass = tk.StringVar()
        ttk.Label(self.tab_register, text="Username").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self.tab_register, textvariable=self.r_user, width=30).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(self.tab_register, text="Password").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self.tab_register, textvariable=self.r_pass, show="•", width=30).grid(row=1, column=1, padx=6, pady=6)
        ttk.Button(self.tab_register, text="Tạo tài khoản", command=self.do_register).grid(row=2, column=0, columnspan=2, pady=10)

        self.status_lbl = ttk.Label(self.login_frame, text="", foreground="#555")
        self.status_lbl.pack(pady=6)

    def do_register(self):
        user = self.r_user.get().strip()
        pw = self.r_pass.get()
        if not user or not pw:
            self.set_status("Vui lòng nhập đủ thông tin đăng ký.")
            return
        try:
            self.net.connect()
            self.net.send("register", {"username": user, "password": pw})
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối được server: {e}")

    def do_login(self):
        user = self.l_user.get().strip()
        pw = self.l_pass.get()
        if not user or not pw:
            self.set_status("Vui lòng nhập username & password.")
            return
        try:
            self.net.connect()
            self.net.send("login", {"username": user, "password": pw})
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối được server: {e}")

    def set_status(self, text):
        if hasattr(self, "status_lbl"):
            self.status_lbl.configure(text=text)

    # ---------- Main UI after login ----------
    def build_main_ui(self):
        if self.main_ui_built:
            return
        self.main_ui_built = True

        if hasattr(self, "login_frame") and self.login_frame.winfo_exists():
            self.login_frame.destroy()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Left panel
        left = ttk.Frame(self, padding=6)
        left.grid(row=0, column=0, sticky="nsw")
        left.columnconfigure(0, weight=1)

        me = ttk.Label(left, text=f"Xin chào, {self.username}", font=("Segoe UI", 12, "bold"))
        me.grid(row=0, column=0, sticky="w", pady=(0,6))

        # Friend controls
        fr_controls = ttk.Frame(left)
        fr_controls.grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(fr_controls, text="Thêm bạn", command=self.ui_add_friend).pack(side="left", padx=2)
        ttk.Button(fr_controls, text="Yêu cầu kết bạn", command=self.ui_show_requests).pack(side="left", padx=2)

        # Room controls
        room_controls = ttk.Frame(left)
        room_controls.grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(room_controls, text="Tạo phòng", command=self.ui_create_room).pack(side="left", padx=2)
        ttk.Button(room_controls, text="Tham gia phòng", command=self.ui_join_room).pack(side="left", padx=2)

        # Search users
        search_controls = ttk.Frame(left)
        search_controls.grid(row=3, column=0, sticky="ew", pady=4)
        self.search_user_var = tk.StringVar()
        ttk.Entry(search_controls, textvariable=self.search_user_var, width=18).pack(side="left", padx=2)
        ttk.Button(search_controls, text="Tìm người dùng", command=self.ui_search_users).pack(side="left", padx=2)

        # Tabs Friends / Rooms
        self.nb_left = ttk.Notebook(left)
        self.tab_friends = ttk.Frame(self.nb_left)
        self.tab_rooms = ttk.Frame(self.nb_left)
        self.nb_left.add(self.tab_friends, text="Bạn bè")
        self.nb_left.add(self.tab_rooms, text="Phòng")
        self.nb_left.grid(row=4, column=0, sticky="nsew", pady=(4,0))
        left.rowconfigure(4, weight=1)

        self.friends_list = tk.Listbox(self.tab_friends, width=28, height=20)
        self.friends_list.pack(fill="both", expand=True)
        self.friends_list.bind("<<ListboxSelect>>", self.on_friend_select)

        self.rooms_list = tk.Listbox(self.tab_rooms, width=28, height=20)
        self.rooms_list.pack(fill="both", expand=True)
        self.rooms_list.bind("<<ListboxSelect>>", self.on_room_select)

        # Right/chat panel
        right = ttk.Frame(self, padding=6)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # Header
        hdr = ttk.Frame(right)
        hdr.grid(row=0, column=0, sticky="ew")
        self.chat_title = ttk.Label(hdr, text="(Chưa chọn hội thoại)", font=("Segoe UI", 12, "bold"))
        self.chat_title.pack(side="left")
        self.typing_lbl = ttk.Label(hdr, text="", foreground="#777")
        self.typing_lbl.pack(side="right")

        # Message area
        self.msg_canvas = tk.Canvas(right, bg="#fbfbfb", highlightthickness=1, highlightbackground="#ddd")
        self.msg_scroll = ttk.Scrollbar(right, orient="vertical", command=self.msg_canvas.yview)
        self.msg_frame = ttk.Frame(self.msg_canvas)
        self.msg_frame.bind("<Configure>", lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all")))
        self.msg_canvas.create_window((0,0), window=self.msg_frame, anchor="nw")
        self.msg_canvas.configure(yscrollcommand=self.msg_scroll.set)
        self.msg_canvas.grid(row=1, column=0, sticky="nsew", pady=(4,4))
        self.msg_scroll.grid(row=1, column=1, sticky="ns", pady=(4,4))

        # Message composer
        comp = ttk.Frame(right)
        comp.grid(row=2, column=0, sticky="ew")
        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(comp, textvariable=self.input_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=2, pady=4)
        self.entry.bind("<KeyPress>", self.on_typing_keypress)
        ttk.Button(comp, text="Ảnh", command=self.ui_send_image).pack(side="left", padx=2)
        ttk.Button(comp, text="File", command=self.ui_send_file).pack(side="left", padx=2)
        ttk.Button(comp, text="Gửi", command=self.ui_send_text).pack(side="left", padx=2)

        # Search in history (keyword + date)
        sr = ttk.Frame(right)
        sr.grid(row=3, column=0, sticky="ew", pady=(4,0))
        ttk.Label(sr, text="Tìm tin nhắn:").pack(side="left")
        self.search_kw = tk.StringVar()
        ttk.Entry(sr, textvariable=self.search_kw, width=24).pack(side="left", padx=4)
        ttk.Label(sr, text="Từ ngày (YYYY-MM-DD):").pack(side="left")
        self.search_from = tk.StringVar()
        ttk.Entry(sr, textvariable=self.search_from, width=12).pack(side="left", padx=2)
        ttk.Label(sr, text="Đến ngày:").pack(side="left")
        self.search_to = tk.StringVar()
        ttk.Entry(sr, textvariable=self.search_to, width=12).pack(side="left", padx=2)
        ttk.Button(sr, text="Tìm", command=self.ui_search_history).pack(side="left", padx=6)

        # Hỏi server danh sách ban đầu
        self.net.send("list_friends", {})
        self.net.send("list_rooms", {})

    # ---------- UI actions ----------
    def on_friend_select(self, _evt):
        sel = self.friends_list.curselection()
        if not sel: return
        item = self.friends_list.get(sel[0])
        uname = item.split(" ")[0]
        self.open_chat("dm", uname)

    def on_room_select(self, _evt):
        sel = self.rooms_list.curselection()
        if not sel: return
        room = self.rooms_list.get(sel[0]).split(" ")[0]
        self.open_chat("room", room)

    def open_chat(self, kind, name):
        self.current_chat = (kind, name)
        self.chat_title.configure(text=f"{'PM' if kind=='dm' else 'Phòng'}: {name}")
        self.typing_lbl.configure(text="")
        cid = self.chat_id(kind, name)
        self.unread[cid] = 0
        self.refresh_lists()
        # fetch history if not cached
        if cid not in self.history:
            self.net.send("fetch_history", {"target_type": kind, "to": name, "limit": 200})
        else:
            self.render_messages(cid)

    def ui_add_friend(self):
        top = tk.Toplevel(self)
        top.title("Thêm bạn")
        tk.Label(top, text="Nhập username:").pack(padx=8, pady=8)
        v = tk.StringVar()
        e = ttk.Entry(top, textvariable=v, width=28); e.pack(padx=8, pady=4); e.focus_set()
        def ok():
            name = v.get().strip()
            if name:
                self.net.send("friend_request", {"to": name})
            top.destroy()
        ttk.Button(top, text="Gửi lời mời", command=ok).pack(padx=8, pady=8)

    def ui_show_requests(self):
        top = tk.Toplevel(self)
        top.title("Yêu cầu kết bạn")
        frm = ttk.Frame(top); frm.pack(padx=8, pady=8)
        ttk.Label(frm, text="Đang chờ bạn chấp nhận:").grid(row=0, column=0, sticky="w")
        lb_in = tk.Listbox(frm, width=24, height=8); lb_in.grid(row=1, column=0, padx=4, pady=4)
        for u in self.incoming: lb_in.insert("end", u)
        ttk.Button(frm, text="Chấp nhận", command=lambda: self._act_req(lb_in, True)).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(frm, text="Từ chối", command=lambda: self._act_req(lb_in, False)).grid(row=3, column=0, sticky="ew", padx=2, pady=2)
        ttk.Label(frm, text="Bạn đã gửi:").grid(row=0, column=1, sticky="w")
        lb_out = tk.Listbox(frm, width=24, height=8); lb_out.grid(row=1, column=1, padx=4, pady=4)
        for u in self.outgoing: lb_out.insert("end", u)
        ttk.Button(frm, text="Đóng", command=top.destroy).grid(row=4, column=0, columnspan=2, pady=6)

    def _act_req(self, lb: tk.Listbox, accept: bool):
        sel = lb.curselection()
        if not sel: return
        u = lb.get(sel[0])
        if accept:
            self.net.send("friend_accept", {"from": u})
        else:
            self.net.send("friend_decline", {"from": u})

    def ui_create_room(self):
        top = tk.Toplevel(self); top.title("Tạo phòng")
        v = tk.StringVar()
        ttk.Label(top, text="Tên phòng:").pack(padx=8, pady=8)
        e = ttk.Entry(top, textvariable=v, width=28); e.pack(padx=8, pady=4); e.focus_set()
        def ok():
            name = v.get().strip()
            if name:
                self.net.send("create_room", {"room": name})
            top.destroy()
        ttk.Button(top, text="Tạo", command=ok).pack(padx=8, pady=8)

    def ui_join_room(self):
        top = tk.Toplevel(self); top.title("Tham gia phòng")
        v = tk.StringVar()
        ttk.Label(top, text="Tên phòng:").pack(padx=8, pady=8)
        e = ttk.Entry(top, textvariable=v, width=28); e.pack(padx=8, pady=4); e.focus_set()
        def ok():
            name = v.get().strip()
            if name:
                self.net.send("join_room", {"room": name})
            top.destroy()
        ttk.Button(top, text="Tham gia", command=ok).pack(padx=8, pady=8)

    def ui_search_users(self):
        q = self.search_user_var.get().strip()
        self.net.send("search_users", {"query": q})

    def ui_send_text(self):
        if not self.current_chat: return
        text = self.input_var.get().strip()
        if not text: return
        kind, name = self.current_chat
        self.net.send("send_message", {"target_type": kind, "to": name, "msgtype":"text", "content": text})
        self.input_var.set("")

    def ui_send_image(self):
        if not self.current_chat: return
        path = filedialog.askopenfilename(title="Chọn ảnh PNG/GIF", filetypes=[("Ảnh", "*.png *.gif"), ("Tất cả", "*.*")])
        if not path: return
        with open(path, "rb") as f:
            b = f.read()
        b64 = base64.b64encode(b).decode("ascii")
        kind, name = self.current_chat
        self.net.send("send_message", {"target_type": kind, "to": name, "msgtype":"image", "filename": os.path.basename(path), "data_base64": b64})

    def ui_send_file(self):
        if not self.current_chat: return
        path = filedialog.askopenfilename(title="Chọn file đính kèm")
        if not path: return
        with open(path, "rb") as f:
            b = f.read()
        b64 = base64.b64encode(b).decode("ascii")
        kind, name = self.current_chat
        self.net.send("send_message", {"target_type": kind, "to": name, "msgtype":"file", "filename": os.path.basename(path), "data_base64": b64})

    def ui_search_history(self):
        if not self.current_chat: return
        kw = self.search_kw.get().strip()
        d1 = self.search_from.get().strip() or None
        d2 = self.search_to.get().strip() or None
        kind, name = self.current_chat
        self.net.send("search_history", {"target_type": kind, "to": name, "keyword": kw, "date_from": d1, "date_to": d2})

    # typing indicator
    def on_typing_keypress(self, _evt):
        if not self.current_chat: return
        kind, name = self.current_chat
        self.net.send("typing", {"target_type": kind, "to": name, "is_typing": True})

    # ---------- Render ----------
    def clear_messages(self):
        for w in self.msg_frame.winfo_children():
            w.destroy()
        self.images_cache.clear()

    def render_messages(self, cid):
        self.clear_messages()
        msgs = self.history.get(cid, [])
        for m in msgs:
            who = m.get("from")
            ts = m.get("ts","")[:19].replace("T"," ")
            left = (who != self.username)
            bubble = ttk.Frame(self.msg_frame)
            bubble.pack(anchor="w" if left else "e", fill="x", pady=2, padx=8)
            head = ttk.Label(bubble, text=f"{who} • {ts}", foreground="#555")
            head.pack(anchor="w" if left else "e")
            if m.get("msgtype") == "text":
                body = tk.Text(bubble, height=2, wrap="word", relief="flat", bg="#f6f6f6")
                body.insert("1.0", m.get("content",""))
                body.configure(state="disabled")
                body.pack(fill="x")
            elif m.get("msgtype") == "image":
                fname = m.get("filename","")
                data = m.get("data_base64")
                lbl = ttk.Label(bubble, text=f"[Ảnh] {fname}")
                lbl.pack(anchor="w")
                ext = os.path.splitext(fname.lower())[1]
                if ext in [".png", ".gif"]:
                    try:
                        img = tk.PhotoImage(data=base64.b64decode(data))
                    except Exception:
                        tmp = os.path.join(os.getcwd(), f"tmp_{fname}")
                        with open(tmp, "wb") as f:
                            f.write(base64.b64decode(data))
                        img = tk.PhotoImage(file=tmp)
                    self.images_cache.append(img)
                    img_lbl = tk.Label(bubble, image=img, bd=1, relief="solid")
                    img_lbl.pack(anchor="w", pady=2)
                btn = ttk.Button(bubble, text="Lưu ảnh", command=lambda d=data, fn=fname: self.save_bytes(d, fn))
                btn.pack(anchor="w")
            elif m.get("msgtype") == "file":
                fname = m.get("filename","(file)")
                ttk.Label(bubble, text=f"[File] {fname}").pack(anchor="w")
                ttk.Button(bubble, text="Lưu file", command=lambda d=m.get("data_base64"), fn=fname: self.save_bytes(d, fn)).pack(anchor="w")
            elif m.get("msgtype") == "typing":
                pass

        self.msg_canvas.update_idletasks()
        self.msg_canvas.yview_moveto(1.0)

    def save_bytes(self, data_b64, filename):
        if not data_b64: return
        path = filedialog.asksaveasfilename(initialfile=filename, title="Lưu")
        if not path: return
        with open(path, "wb") as f:
            f.write(base64.b64decode(data_b64))
        messagebox.showinfo("Lưu file", f"Đã lưu: {path}")

    def refresh_lists(self):
        # friends
        if hasattr(self, "friends_list"):
            self.friends_list.delete(0, "end")
            for u in sorted(self.friends.keys()):
                status = "🟢" if self.friends[u] else "⚫"
                cid = self.chat_id("dm", u)
                unread = self.unread.get(cid, 0)
                dot = f"  ({unread})" if unread else ""
                self.friends_list.insert("end", f"{u} {status}{dot}")
        # rooms
        if hasattr(self, "rooms_list"):
            self.rooms_list.delete(0, "end")
            for r in sorted(self.rooms):
                cid = self.chat_id("room", r)
                unread = self.unread.get(cid, 0)
                dot = f"  ({unread})" if unread else ""
                self.rooms_list.insert("end", f"{r}{dot}")

    # ---------- Event handler from server ----------
    def ensure_main_ui(self):
        """Gọi an toàn để chắc chắn UI chính được dựng sau đăng nhập."""
        if not self.main_ui_built and self.username:
            self.build_main_ui()

    def handle_event(self, obj):
        t = obj.get("type")
        if t == "system":
            msg = obj.get("message","")
            if not self.username:
                self.set_status(msg)
            else:
                # Chỉ thông báo nhẹ để tránh che UI khi spam
                if msg:
                    print("[SYSTEM]", msg)
        elif t == "register":
            if obj.get("ok"):
                self.set_status("Đăng ký thành công. Vui lòng đăng nhập.")
            else:
                self.set_status(f"Đăng ký thất bại: {obj.get('error')}")
        elif t == "login":
            if obj.get("ok"):
                self.username = obj.get("username")
                self.ensure_main_ui()
                # Sau khi dựng UI, yêu cầu danh sách
                self.net.send("list_friends", {})
                self.net.send("list_rooms", {})
                self.set_status("")
            else:
                self.set_status(f"Đăng nhập thất bại: {obj.get('error')}")
        elif t == "friend_list":
            # Nếu vì lý do nào đó friend_list đến trước login(ok) ➜ vẫn dựng UI
            self.ensure_main_ui()
            self.friends = {f["username"]: bool(f["online"]) for f in obj.get("friends", [])}
            self.incoming = obj.get("incoming", [])
            self.outgoing = obj.get("outgoing", [])
            self.refresh_lists()
        elif t == "friend_request":
            self.ensure_main_ui()
            who = obj.get("from")
            if who and who not in self.incoming:
                self.incoming.append(who)
            self.safe_bell()
            messagebox.showinfo("Yêu cầu kết bạn", f"{who} muốn kết bạn.")
            self.net.send("list_friends", {})
        elif t in ("friend_accept","friend_decline","friend_remove"):
            self.ensure_main_ui()
            self.net.send("list_friends", {})
        elif t == "room_list":
            self.ensure_main_ui()
            self.rooms = obj.get("rooms", [])
            self.refresh_lists()
        elif t == "room_update":
            self.ensure_main_ui()
            self.net.send("list_rooms", {})
        elif t == "presence":
            self.ensure_main_ui()
            u = obj.get("user")
            on = bool(obj.get("online"))
            if u in self.friends:
                self.friends[u] = on
                self.refresh_lists()
        elif t == "new_message":
            self.ensure_main_ui()
            m = obj.get("message", {})
            kind = m.get("target_type")
            to = m.get("to")
            sender = m.get("from")
            if kind == "dm":
                chat_partner = sender if sender != self.username else to
                cid = self.chat_id("dm", chat_partner)
            else:
                cid = self.chat_id("room", to)

            lst = self.history.setdefault(cid, [])
            if m.get("msgtype") != "typing":
                lst.append(m)

            if m.get("msgtype") == "typing":
                if self.current_chat and self.chat_id(*self.current_chat) == cid:
                    who = m.get("from")
                    self.typing_lbl.configure(text=f"{who} đang nhập...")
                    self.after(1200, lambda: self.typing_lbl.configure(text=""))
                return

            if not self.current_chat or self.chat_id(*self.current_chat) != cid:
                self.unread[cid] = self.unread.get(cid, 0) + 1
                self.refresh_lists()
                self.safe_bell()
            else:
                self.render_messages(cid)
        elif t == "fetch_history":
            self.ensure_main_ui()
            if obj.get("ok") and self.current_chat:
                cid = self.chat_id(*self.current_chat)
                self.history[cid] = obj.get("messages", [])
                self.render_messages(cid)
        elif t == "search_users":
            self.ensure_main_ui()
            res = obj.get("results", [])
            top = tk.Toplevel(self); top.title("Kết quả tìm kiếm người dùng")
            lb = tk.Listbox(top, width=30, height=12); lb.pack(padx=8, pady=8)
            for u in res:
                if u != self.username:
                    lb.insert("end", u)
            ttk.Button(top, text="Kết bạn", command=lambda: self._req_from_list(lb, top)).pack(pady=6)
        elif t == "search_history":
            self.ensure_main_ui()
            if not self.current_chat: return
            cid = self.chat_id(*self.current_chat)
            msgs = obj.get("messages", [])
            self.history[cid] = msgs
            self.render_messages(cid)
        else:
            pass

    def _req_from_list(self, lb, top):
        sel = lb.curselection()
        if not sel: return
        u = lb.get(sel[0])
        self.net.send("friend_request", {"to": u})
        top.destroy()

# ------------- Run -------------
if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
