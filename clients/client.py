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

# ---------------- Networking ----------------
class NetClient:
    def __init__(self, host, port, on_event):
        self.host = host
        self.port = port
        self.on_event = on_event
        self.sock = None
        self.fp = None
        self.connected = False
        self.lock = threading.RLock()

    def connect(self):
        if self.connected:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.fp = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self.connected = True
        threading.Thread(target=self._rx_loop, daemon=True).start()

    def _rx_loop(self):
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
            self.on_event({"type": "system", "message": "Mất kết nối server."})

    def send(self, typ, payload):
        if not self.connected:
            self.connect()
        data = (json.dumps({"type": typ, "payload": payload}, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            self.sock.sendall(data)

    def close(self):
        try:
            with self.lock:
                if self.sock:
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    self.sock.close()
        except Exception:
            pass
        self.connected = False
        self.sock = None
        self.fp = None

# ---------------- App & GUI ----------------
class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Socket Chat Client")
        self.geometry("1000x640")
        self.minsize(900, 560)

        # --- ttk style: sáng, bo góc nhẹ ---
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 10))
        style.configure("Accent.TButton", padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=4)
        style.configure("Card.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        style.map("TButton", relief=[("pressed", "sunken"), ("active", "raised")])

        self.net = NetClient(HOST, PORT, self.enqueue_event)
        self.event_q = queue.Queue()

        # state
        self.username = None
        self.main_ui_built = False
        # friends: dict[id] = {"online": bool, "full_name": str or None}
        self.friends = {}
        self.incoming = []
        self.outgoing = []

        # rooms: dict[room_id] = room_name
        self.rooms = {}
        self.current_chat = None              # ("dm", id) hoặc ("room", room_id)
        self.history = {}                     # key = "dm:id" | "room:room_id"
        self.unread = {}
        self.images_cache = []

        # mapping hiển thị
        self.friend_index = []
        self.room_index = []
        self.search_index = []

        # ====== THEME SÁNG ======
        # nền tổng thể
        self.app_bg         = "#f5f7fb"   # nền cửa sổ
        self.sidebar_bg     = "#ffffff"   # nền panel trái
        self.chat_bg        = "#f9fafc"   # nền vùng chat (canvas)
        # màu chữ
        self.text_primary   = "#1f2937"
        self.text_muted     = "#6b7280"
        # bong bóng
        self.self_bubble_bg   = "#3b82f6"   # xanh dương
        self.self_text_fg     = "#ffffff"
        self.other_bubble_bg  = "#e5e7eb"   # xám nhạt
        self.other_text_fg    = "#111827"
        # viền/độ cong
        self.bubble_radius  = 16
        self.bubble_pad_xy  = (14, 10)
        self.bubble_wrap_w  = 520
        self.row_pad_x      = 10
        self.row_pad_y      = 6
        self.time_fg        = "#9aa0a6"

        self.configure(bg=self.app_bg)

        # containers
        self.login_frame = None
        self.main_container = None

        # build
        self.build_login_ui()
        self.after(80, self.process_events)

    # ---- util ----
    def chat_id(self, kind, name): return f"{kind}:{name}"
    def enqueue_event(self, obj): self.event_q.put(obj)
    def process_events(self):
        while not self.event_q.empty():
            self.handle_event(self.event_q.get())
        self.after(80, self.process_events)

    def _now_iso_local(self):
        return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    def _hhmm_from_iso(self, ts):
        try:
            return ts[11:16]
        except Exception:
            return ts

    # ---- login ui (giữ giống trước) ----
    def build_login_ui(self):
        self.destroy_main_container()
        self.login_frame = ttk.Frame(self)
        self.login_frame.pack(fill="both", expand=True)

        container = ttk.Frame(self.login_frame)
        container.place(relx=0.5, rely=0.22, anchor="n")
        for i in range(2):
            container.columnconfigure(i, weight=1)

        ttk.Label(container, text="Đăng nhập / Đăng ký", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16)
        )

        # Biến dữ liệu dùng chung
        self.u_var = tk.StringVar()
        self.p_var = tk.StringVar()
        self.e_var = tk.StringVar()  # Email khi đăng ký

        ttk.Label(container, text="Username").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        ent_user = ttk.Entry(container, textvariable=self.u_var, width=36)
        ent_user.grid(row=1, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(container, text="Password").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        ent_pass = ttk.Entry(container, textvariable=self.p_var, show="•", width=36)
        ent_pass.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(container, text="Email (khi đăng ký)").grid(row=3, column=0, sticky="e", padx=8, pady=6)
        ent_email = ttk.Entry(container, textvariable=self.e_var, width=36)
        ent_email.grid(row=3, column=1, sticky="w", padx=8, pady=6)

        btn_row = ttk.Frame(container)
        btn_row.grid(row=4, column=0, columnspan=2, pady=12)

        ttk.Button(btn_row, text="Kết nối", command=self.do_connect).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Đăng nhập", style="Accent.TButton", command=self.do_login).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Đăng ký", command=self.do_register).pack(side="left", padx=4)

        self.status_lbl = ttk.Label(container, text="Chưa kết nối", foreground=self.text_muted)
        self.status_lbl.grid(row=5, column=0, columnspan=2, pady=(6, 0))

        # Enter để đăng nhập nhanh
        ent_user.bind("<Return>", lambda e: self.do_login())
        ent_pass.bind("<Return>", lambda e: self.do_login())

    def set_status(self, text):
        if self.login_frame and self.login_frame.winfo_exists():
            self.status_lbl.configure(text=text)

    # nút "Kết nối"
    def do_connect(self):
        try:
            if not self.net.connected:
                self.net.connect()
            self.set_status("Đã kết nối server.")
        except Exception as e:
            self.set_status(f"Lỗi kết nối: {e}")

    def do_register(self):
        u = self.u_var.get().strip()
        p = self.p_var.get()
        email = self.e_var.get().strip()
        if not u or not p or not email:
            self.set_status("Nhập đủ Username, Password và Email.")
            return
        try:
            self.net.connect()
            payload = {"username": u, "password": p, "full_name": email}
            # nếu server có field email riêng:
            # payload["email"] = email
            self.net.send("register", payload)
            self.set_status("Đang gửi yêu cầu đăng ký...")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối được server: {e}")

    def do_login(self):
        u = self.u_var.get().strip()
        p = self.p_var.get()
        if not u or not p:
            self.set_status("Nhập Username & Password.")
            return
        try:
            self.net.connect()
            self.net.send("login", {"username": u, "password": p})
            self.set_status("Đang đăng nhập...")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối được server: {e}")

    # ---- main ui (SÁNG – không nền đen) ----
    def build_main_ui(self):
        if self.main_ui_built: return
        self.main_ui_built = True
        if self.login_frame and self.login_frame.winfo_exists():
            self.login_frame.destroy()

        self.configure(bg=self.app_bg)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.main_container = ttk.Frame(self, padding=8)
        self.main_container.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # ===== Header top bar =====
        topbar = ttk.Frame(self.main_container)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        topbar.columnconfigure(0, weight=1)
        title = ttk.Label(topbar, text=f"Xin chào, {self.username}", font=("Segoe UI", 14, "bold"), foreground=self.text_primary)
        title.grid(row=0, column=0, sticky="w")
        self.req_badge_var = tk.StringVar(value="0")
        ttk.Button(topbar, text="Yêu cầu: ", state="disabled").grid(row=0, column=1, sticky="e")
        ttk.Button(topbar, textvariable=self.req_badge_var, width=4, command=self.ui_show_requests).grid(row=0, column=2, sticky="e", padx=(4,0))

        # ===== Left sidebar (card) =====
        left_card = ttk.Frame(self.main_container, style="Card.TFrame")
        left_card.grid(row=1, column=0, sticky="nsw", padx=(0,8))
        left = ttk.Frame(left_card, padding=10)
        left.pack(fill="both", expand=True)

        # Actions
        act = ttk.Frame(left)
        act.pack(fill="x", pady=(0,6))
        ttk.Button(act, text="➕ Thêm bạn", command=self.ui_add_friend).pack(side="left", padx=2)
        ttk.Button(act, text="📨 Yêu cầu", command=self.ui_show_requests).pack(side="left", padx=2)
        ttk.Button(act, text="⎋ Đăng xuất", command=self.ui_logout).pack(side="right", padx=2)

        # Rooms actions
        ract = ttk.Frame(left)
        ract.pack(fill="x", pady=6)
        ttk.Button(ract, text="🏠 Tạo phòng", command=self.ui_create_room).pack(side="left", padx=2)
        ttk.Button(ract, text="🔑 Tham gia (ID)", command=self.ui_join_room).pack(side="left", padx=2)
        ttk.Button(ract, text="🚪 Rời phòng", command=self.ui_leave_room).pack(side="left", padx=2)

        # Search user
        srow = ttk.Frame(left)
        srow.pack(fill="x", pady=(6,4))
        ttk.Label(srow, text="Tìm theo ID:").pack(side="left")
        self.search_user_var = tk.StringVar()
        ent = ttk.Entry(srow, textvariable=self.search_user_var, width=18)
        ent.pack(side="left", padx=6)
        ent.bind("<Return>", lambda e: self.ui_search_users())
        ttk.Button(srow, text="Tìm", command=self.ui_search_users).pack(side="left")

        # Lists
        self.nb_left = ttk.Notebook(left)
        self.tab_friends = ttk.Frame(self.nb_left); self.tab_rooms = ttk.Frame(self.nb_left)
        self.nb_left.add(self.tab_friends, text="Bạn bè"); self.nb_left.add(self.tab_rooms, text="Phòng")
        self.nb_left.pack(fill="both", expand=True, pady=(6,0))

        self.friends_list = tk.Listbox(self.tab_friends, width=28, height=20, bd=0, highlightthickness=0)
        self.friends_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.friends_list.bind("<<ListboxSelect>>", self.on_friend_select)

        self.rooms_list = tk.Listbox(self.tab_rooms, width=28, height=20, bd=0, highlightthickness=0)
        self.rooms_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.rooms_list.bind("<<ListboxSelect>>", self.on_room_select)

        # ===== Right chat area (card) =====
        right_card = ttk.Frame(self.main_container, style="Card.TFrame")
        right_card.grid(row=1, column=1, sticky="nsew")
        self.main_container.columnconfigure(1, weight=1)
        self.main_container.rowconfigure(1, weight=1)

        right = tk.Frame(right_card, bg=self.chat_bg, highlightthickness=0, bd=0)
        right.pack(fill="both", expand=True)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # Header chat
        hdr = tk.Frame(right, bg=self.chat_bg)
        hdr.grid(row=0, column=0, sticky="ew")
        self.status_dot = tk.Canvas(hdr, width=12, height=12, bg=self.chat_bg, highlightthickness=0, bd=0)
        self.status_dot.pack(side="left", padx=(12,4), pady=14)
        self.status_dot_id = self.status_dot.create_oval(2,2,10,10, fill="#a3a3a3", outline="")
        self.chat_title = tk.Label(hdr, text="(Chưa chọn hội thoại)", font=("Segoe UI", 12, "bold"),
                                   fg=self.text_primary, bg=self.chat_bg)
        self.chat_title.pack(side="left", padx=6, pady=10)
        self.typing_lbl = tk.Label(hdr, text="", fg=self.text_muted, bg=self.chat_bg)
        self.typing_lbl.pack(side="right", padx=10, pady=10)

        # Vùng tin nhắn
        self.msg_canvas = tk.Canvas(right, bg=self.chat_bg, highlightthickness=0, bd=0)
        self.msg_scroll = ttk.Scrollbar(right, orient="vertical", command=self.msg_canvas.yview)
        self.msg_holder = tk.Frame(self.msg_canvas, bg=self.chat_bg)
        self.msg_window = self.msg_canvas.create_window((0,0), window=self.msg_holder, anchor="nw")
        self.msg_holder.bind("<Configure>", lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all")))
        self.msg_canvas.bind("<Configure>", self._sync_msg_width)
        self._bind_mouse_wheel(self.msg_canvas)

        self.msg_canvas.configure(yscrollcommand=self.msg_scroll.set)
        self.msg_canvas.grid(row=1, column=0, sticky="nsew"); self.msg_scroll.grid(row=1, column=1, sticky="ns")

        # Composer
        comp = tk.Frame(right, bg=self.chat_bg)
        comp.grid(row=2, column=0, sticky="ew", pady=(6,10), padx=10)
        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(comp, textvariable=self.input_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0,8))
        self.entry.bind("<KeyPress>", self.on_typing_keypress)
        ttk.Button(comp, text="Ảnh", command=self.ui_send_image).pack(side="left", padx=2)
        ttk.Button(comp, text="File", command=self.ui_send_file).pack(side="left", padx=2)
        ttk.Button(comp, text="Gửi", style="Accent.TButton", command=self.ui_send_text).pack(side="left", padx=(6,0))

        # yêu cầu danh sách ban đầu
        self.net.send("list_friends", {})
        self.net.send("list_rooms", {})

    # keep the inner frame width equal to canvas width
    def _sync_msg_width(self, event):
        try:
            self.msg_canvas.itemconfigure(self.msg_window, width=event.width)
        except Exception:
            pass

    # enable mouse wheel scrolling
    def _bind_mouse_wheel(self, widget):
        def _on_mousewheel(e):
            if e.num == 5 or e.delta < 0:
                widget.yview_scroll(1, "units")
            else:
                widget.yview_scroll(-1, "units")
        widget.bind("<MouseWheel>", _on_mousewheel)      # Windows / macOS
        widget.bind("<Button-4>", _on_mousewheel)        # Linux up
        widget.bind("<Button-5>", _on_mousewheel)        # Linux down

    # ---- destroy / reset ----
    def destroy_main_container(self):
        if self.main_container and self.main_container.winfo_exists():
            self.main_container.destroy()
        self.main_ui_built = False

    def reset_state(self):
        self.username = None
        self.friends = {}
        self.incoming = []
        self.outgoing = []
        self.rooms = {}
        self.current_chat = None
        self.history = {}
        self.unread = {}
        self.images_cache = []
        self.friend_index = []
        self.room_index = []
        self.search_index = []

    def reset_to_login(self):
        self.net.close()
        self.destroy_main_container()
        self.reset_state()
        self.build_login_ui()

    # ---- UI actions ----
    def ui_logout(self):
        try:
            self.net.send("logout", {})
        except Exception:
            self.reset_to_login()

    def on_friend_select(self, _):
        sel = self.friends_list.curselection()
        if not sel: return
        idx = sel[0]
        if idx < 0 or idx >= len(self.friend_index): return
        uname = self.friend_index[idx]
        self.open_chat("dm", uname)

    def on_room_select(self, _):
        sel = self.rooms_list.curselection()
        if not sel: return
        idx = sel[0]
        if idx < 0 or idx >= len(self.room_index): return
        room_id = self.room_index[idx]
        self.open_chat("room", room_id)

    def _update_header_online(self):
        """Chấm online (xanh) khi đang chat DM và đối phương online."""
        color_off = "#a3a3a3"
        color_on = "#10b981"
        col = color_off
        if self.current_chat and self.current_chat[0] == "dm":
            uid = self.current_chat[1]
            if self.friends.get(uid, {}).get("online"):
                col = color_on
        self.status_dot.itemconfig(self.status_dot_id, fill=col, outline=col)

    def open_chat(self, kind, name):
        self.current_chat = (kind, name)
        if kind == "dm":
            display = self.friends.get(name, {}).get("full_name") or name
        else:
            room_name = self.rooms.get(name) or name
            display = f"{room_name} ({name})"
        self.chat_title.configure(text=f"{'PM' if kind=='dm' else 'Phòng'}: {display}")
        self._update_header_online()

        cid = self.chat_id(kind, name)
        self.unread[cid] = 0
        self.refresh_lists()
        if cid not in self.history:
            self.net.send("fetch_history", {"target_type": kind, "to": name, "limit": 200})
        else:
            self.render_messages(cid)

    def ui_add_friend(self):
        top = tk.Toplevel(self); top.title("Thêm bạn")
        tk.Label(top, text="Nhập ID đăng nhập:").pack(padx=8, pady=8)
        v = tk.StringVar()
        e = ttk.Entry(top, textvariable=v, width=28); e.pack(padx=8, pady=4); e.focus_set()
        def ok():
            name = v.get().strip()
            if name:
                self.net.send("friend_request", {"to": name})
            top.destroy()
        ttk.Button(top, text="Gửi lời mời", command=ok).pack(padx=8, pady=8)

    def ui_show_requests(self):
        top = tk.Toplevel(self); top.title("Yêu cầu kết bạn")
        frm = ttk.Frame(top); frm.pack(padx=8, pady=8)
        ttk.Label(frm, text="Đang chờ bạn chấp nhận (ID):").grid(row=0, column=0, sticky="w")
        lb_in = tk.Listbox(frm, width=28, height=8); lb_in.grid(row=1, column=0, padx=4, pady=4)
        for u in self.incoming: lb_in.insert("end", u)
        ttk.Button(frm, text="Chấp nhận", command=lambda: self._act_req(lb_in, True)).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(frm, text="Từ chối", command=lambda: self._act_req(lb_in, False)).grid(row=3, column=0, sticky="ew", padx=2, pady=2)

        ttk.Label(frm, text="Bạn đã gửi (chờ đối phương duyệt) (ID):").grid(row=0, column=1, sticky="w")
        lb_out = tk.Listbox(frm, width=28, height=8); lb_out.grid(row=1, column=1, padx=4, pady=4)
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
                self.net.send("create_room", {"room_name": name})
            top.destroy()
        ttk.Button(top, text="Tạo", command=ok).pack(padx=8, pady=8)

    def ui_join_room(self):
        top = tk.Toplevel(self); top.title("Tham gia phòng bằng ID")
        v = tk.StringVar()
        ttk.Label(top, text="ID phòng (4 số):").pack(padx=8, pady=8)
        e = ttk.Entry(top, textvariable=v, width=12); e.pack(padx=8, pady=4); e.focus_set()
        def ok():
            rid = v.get().strip()
            if rid:
                self.net.send("join_room", {"room_id": rid})
            top.destroy()
        ttk.Button(top, text="Tham gia", command=ok).pack(padx=8, pady=8)

    def ui_leave_room(self):
        if not self.current_chat or self.current_chat[0] != "room":
            messagebox.showinfo("Rời phòng", "Hãy chọn một phòng trong danh sách trước.")
            return
        room_id = self.current_chat[1]
        if messagebox.askyesno("Rời phòng", f"Bạn muốn rời phòng '{self.rooms.get(room_id, room_id)}' (ID {room_id})?"):
            self.net.send("leave_room", {"room_id": room_id})

    def ui_search_users(self):
        q = self.search_user_var.get().strip()
        self.net.send("search_users", {"query": q})

    # ---------- gửi tin nhắn (optimistic UI cho DM) ----------
    def _append_local_message(self, target_type, to, msgtype, content=None, filename=None, data_b64=None):
        if target_type != "dm":
            return
        ts = self._now_iso_local()
        msg = {
            "from": self.username,
            "to": to,
            "target_type": "dm",
            "msgtype": msgtype,
            "content": content or "",
            "filename": filename,
            "data_base64": data_b64,
            "ts": ts
        }
        cid = self.chat_id("dm", to)
        self.history.setdefault(cid, []).append(msg)
        if self.current_chat and self.chat_id(*self.current_chat) == cid:
            self.render_messages(cid)

    def ui_send_text(self):
        if not self.current_chat: return
        text = self.input_var.get().strip()
        if not text: return
        k, name = self.current_chat
        self.net.send("send_message", {"target_type": k, "to": name, "msgtype": "text", "content": text})
        self._append_local_message(k, name, "text", content=text)   # hiện ngay
        self.input_var.set("")

    def ui_send_image(self):
        if not self.current_chat: return
        path = filedialog.askopenfilename(title="Chọn ảnh PNG/GIF", filetypes=[("Ảnh", "*.png *.gif"), ("Tất cả", "*.*")])
        if not path: return
        with open(path, "rb") as f: b = f.read()
        b64 = base64.b64encode(b).decode("ascii")
        k, name = self.current_chat
        self.net.send("send_message", {"target_type": k, "to": name, "msgtype": "image", "filename": os.path.basename(path), "data_base64": b64})
        self._append_local_message(k, name, "image", filename=os.path.basename(path), data_b64=b64)

    def ui_send_file(self):
        if not self.current_chat: return
        path = filedialog.askopenfilename(title="Chọn file đính kèm")
        if not path: return
        with open(path, "rb") as f: b = f.read()
        b64 = base64.b64encode(b).decode("ascii")
        k, name = self.current_chat
        self.net.send("send_message", {"target_type": k, "to": name, "msgtype": "file", "filename": os.path.basename(path), "data_base64": b64})
        self._append_local_message(k, name, "file", filename=os.path.basename(path), data_b64=b64)

    def on_typing_keypress(self, _):
        if not self.current_chat: return
        k, name = self.current_chat
        self.net.send("typing", {"target_type": k, "to": name, "is_typing": True})

    # ====== BONG BÓNG ======
    def _draw_round_rect(self, canvas, x1, y1, x2, y2, r, fill):
        points = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
            x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1
        ]
        return canvas.create_polygon(points, smooth=True, fill=fill, outline=fill)

    def _add_time_divider(self, parent, text):
        row = tk.Frame(parent, bg=self.chat_bg)
        row.pack(fill="x", pady=(4,2))
        lbl = tk.Label(row, text=text, bg=self.chat_bg, fg=self.text_muted, font=("Segoe UI", 9))
        lbl.pack(pady=2)
        return row

    def _add_text_bubble(self, parent, text, is_self):
        row = tk.Frame(parent, bg=self.chat_bg)
        row.pack(fill="x", padx=self.row_pad_x, pady=self.row_pad_y)

        anchor = "e" if is_self else "w"
        side   = "right" if is_self else "left"

        hold = tk.Frame(row, bg=self.chat_bg)
        hold.pack(anchor=anchor, fill="x")

        c = tk.Canvas(hold, bg=self.chat_bg, highlightthickness=0, bd=0)
        c.pack(side=side)

        pad_x, pad_y = self.bubble_pad_xy
        text_id = c.create_text(
            pad_x, pad_y, text=text,
            fill=(self.self_text_fg if is_self else self.other_text_fg),
            font=("Segoe UI", 11),
            width=self.bubble_wrap_w, anchor="nw", justify="left"
        )
        c.update_idletasks()
        bbox = c.bbox(text_id)
        text_w = max(0, bbox[2] - bbox[0])
        w = min(self.bubble_wrap_w, text_w + pad_x*2)
        h = (bbox[3] - bbox[1]) + pad_y*2

        c.configure(width=w, height=h)
        self._draw_round_rect(
            c, 0, 0, w, h, self.bubble_radius,
            fill=(self.self_bubble_bg if is_self else self.other_bubble_bg)
        )
        c.tag_raise(text_id)

    def _add_file_bubble(self, parent, filename, data_b64, is_self):
        txt = f"📎 {filename}"
        self._add_text_bubble(parent, txt, is_self)
        row = tk.Frame(parent, bg=self.chat_bg)
        row.pack(fill="x", padx=self.row_pad_x, pady=(0, self.row_pad_y))
        btn = ttk.Button(row, text="Tải xuống", command=lambda d=data_b64, fn=filename: self.save_bytes(d, fn))
        if is_self:
            btn.pack(anchor="e", padx=6)
        else:
            btn.pack(anchor="w", padx=6)

    def _add_image_bubble(self, parent, filename, data_b64, is_self):
        try:
            im = tk.PhotoImage(data=base64.b64decode(data_b64))
        except Exception:
            tmp = os.path.join(os.getcwd(), f"_tmp_{filename}")
            with open(tmp, "wb") as f: f.write(base64.b64decode(data_b64))
            im = tk.PhotoImage(file=tmp)
        self.images_cache.append(im)

        maxw = self.bubble_wrap_w
        w, h = im.width(), im.height()
        if w > maxw and w > 0:
            ratio = max(1, int((w + maxw - 1)//maxw))
            im = im.subsample(ratio, ratio)
            self.images_cache.append(im)
            w, h = im.width(), im.height()

        row = tk.Frame(parent, bg=self.chat_bg)
        row.pack(fill="x", padx=self.row_pad_x, pady=self.row_pad_y)

        anchor = "e" if is_self else "w"
        side   = "right" if is_self else "left"

        hold = tk.Frame(row, bg=self.chat_bg)
        hold.pack(anchor=anchor, fill="x")

        c = tk.Canvas(hold, bg=self.chat_bg, highlightthickness=0, bd=0, width=w + 28, height=h + 28)
        c.pack(side=side)

        self._draw_round_rect(c, 0, 0, w + 28, h + 28, self.bubble_radius,
                              fill=(self.self_bubble_bg if is_self else self.other_bubble_bg))
        c.create_image(14, 14, anchor="nw", image=im)

        row2 = tk.Frame(parent, bg=self.chat_bg)
        row2.pack(fill="x", padx=self.row_pad_x, pady=(0, self.row_pad_y))
        btn = ttk.Button(row2, text="Tải ảnh", command=lambda d=data_b64, fn=filename: self.save_bytes(d, fn))
        if is_self:
            btn.pack(anchor="e", padx=6)
        else:
            btn.pack(anchor="w", padx=6)

    # ---- render & lists ----
    def clear_messages(self):
        for w in self.msg_holder.winfo_children():
            w.destroy()
        self.images_cache.clear()

    def render_messages(self, cid):
        self.clear_messages()
        msgs = self.history.get(cid, [])

        last_sender = None
        for m in msgs:
            who = m.get("from")
            is_self = (who == self.username)
            ts = m.get("ts","")
            hhmm = self._hhmm_from_iso(ts)

            if last_sender is None or who != last_sender:
                self._add_time_divider(self.msg_holder, hhmm)
            last_sender = who

            mt = m.get("msgtype")
            if mt == "text":
                self._add_text_bubble(self.msg_holder, m.get("content",""), is_self)
            elif mt == "image":
                self._add_image_bubble(self.msg_holder, m.get("filename",""), m.get("data_base64"), is_self)
            elif mt == "file":
                self._add_file_bubble(self.msg_holder, m.get("filename","(file)"), m.get("data_base64"), is_self)

        self.msg_canvas.update_idletasks()
        self.msg_canvas.yview_moveto(1.0)

    def save_bytes(self, data_b64, filename):
        if not data_b64: return
        path = filedialog.asksaveasfilename(initialfile=filename, title="Lưu")
        if not path: return
        with open(path, "wb") as f: f.write(base64.b64decode(data_b64))
        messagebox.showinfo("Lưu file", f"Đã lưu: {path}")

    def refresh_lists(self):
        # Bạn bè (hiển thị Họ Tên + chấm 🟢/⚫)
        if self.friends_list and self.friends_list.winfo_exists():
            self.friends_list.delete(0, "end")
            self.friend_index = []
            def display_name(uid):
                return (self.friends.get(uid, {}).get("full_name") or uid).lower()
            for uid in sorted(self.friends.keys(), key=display_name):
                info = self.friends[uid]
                name = info.get("full_name") or uid
                dot = "🟢" if info.get("online") else "⚫"
                cid = self.chat_id("dm", uid)
                badge = f"  ({self.unread.get(cid,0)})" if self.unread.get(cid,0) else ""
                self.friends_list.insert("end", f"{name} {dot}{badge}")
                self.friend_index.append(uid)

        # Phòng
        if self.rooms_list and self.rooms_list.winfo_exists():
            self.rooms_list.delete(0, "end")
            self.room_index = []
            for rid, rname in sorted(self.rooms.items(), key=lambda kv: kv[1].lower()):
                cid = self.chat_id("room", rid)
                badge = f"  ({self.unread.get(cid,0)})" if self.unread.get(cid,0) else ""
                self.rooms_list.insert("end", f"{rname}{badge}")
                self.room_index.append(rid)

        if hasattr(self, "req_badge_var") and self.req_badge_var:
            self.req_badge_var.set(str(len(self.incoming)))

        self._update_header_online()

    def ensure_main_ui(self):
        if not self.main_ui_built and self.username:
            self.build_main_ui()

    # ---- event handler ----
    def handle_event(self, obj):
        t = obj.get("type")

        if t == "system":
            msg = obj.get("message","")
            if not self.username: self.set_status(msg)
            return

        if t == "register":
            self.set_status("Đăng ký thành công. Vui lòng đăng nhập." if obj.get("ok") else f"Đăng ký thất bại: {obj.get('error')}")
            return

        if t == "login":
            if obj.get("ok"):
                self.username = obj.get("username")
                self.ensure_main_ui()
                self.net.send("list_friends", {}); self.net.send("list_rooms", {})
                self.set_status("")
            else:
                self.set_status(f"Đăng nhập thất bại: {obj.get('error')}")
            return

        if t == "logout":
            self.reset_to_login()
            return

        self.ensure_main_ui()

        if t == "friend_list":
            self.friends = {}
            raw = obj.get("friends", [])
            for item in raw:
                if isinstance(item, dict):
                    uid = item.get("username")
                    if not uid: continue
                    self.friends[uid] = {
                        "online": bool(item.get("online")),
                        "full_name": item.get("full_name") or item.get("name")
                    }
                else:
                    uid = str(item)
                    self.friends[uid] = {"online": False, "full_name": None}
            self.incoming = obj.get("incoming", [])
            self.outgoing = obj.get("outgoing", [])
            self.refresh_lists()
            return

        if t == "friend_request":
            who = obj.get("from")
            if who and who not in self.incoming:
                self.incoming.append(who)
            self.refresh_lists()
            messagebox.showinfo("Yêu cầu kết bạn", f"{who} đã gửi lời mời kết bạn cho bạn.")
            self.net.send("list_friends", {})
            return

        if t == "friend_accept":
            self.net.send("list_friends", {})
            return

        if t == "friend_decline":
            self.net.send("list_friends", {})
            return

        if t == "room_list":
            self.rooms = {}
            for r in obj.get("rooms", []):
                if isinstance(r, dict) and r.get("id"):
                    self.rooms[str(r["id"])] = r.get("name") or str(r["id"])
                elif isinstance(r, str):
                    self.rooms[str(r)] = str(r)
            self.refresh_lists()
            return

        if t == "create_room":
            if obj.get("ok"):
                room = obj.get("room", {})
                rid = str(room.get("id"))
                rname = room.get("name")
                messagebox.showinfo("Tạo phòng", f"Đã tạo phòng '{rname}' với ID {rid}.")
                self.net.send("list_rooms", {})
            else:
                messagebox.showerror("Tạo phòng", obj.get("error","Tạo phòng thất bại"))
            return

        if t == "join_room":
            if obj.get("ok"):
                room = obj.get("room", {})
                rid = str(room.get("id"))
                rname = room.get("name")
                messagebox.showinfo("Tham gia phòng", f"Đã tham gia '{rname}' (ID {rid}).")
                self.net.send("list_rooms", {})
            else:
                messagebox.showerror("Tham gia phòng", obj.get("error","Không tham gia được"))
            return

        if t == "leave_room":
            if obj.get("ok"):
                messagebox.showinfo("Rời phòng", "Đã rời phòng.")
                if self.current_chat and self.current_chat[0] == "room":
                    rid = self.current_chat[1]
                    if rid not in self.rooms:
                        self.current_chat = None
                        self.chat_title.configure(text="(Chưa chọn hội thoại)")
                        self.clear_messages()
                self.net.send("list_rooms", {})
            else:
                messagebox.showerror("Rời phòng", obj.get("error","Không rời được phòng"))
            return

        if t == "room_update":
            self.net.send("list_rooms", {})
            return

        if t == "presence":
            u = obj.get("user"); on = bool(obj.get("online"))
            if u in self.friends:
                self.friends[u]["online"] = on
                self.refresh_lists()
            return

        if t == "new_message":
            m = obj.get("message", {})
            kind = m.get("target_type")
            to = m.get("to")
            sender = m.get("from")
            if m.get("msgtype") == "typing":
                if self.current_chat:
                    cid_cur = self.chat_id(*self.current_chat)
                    if (kind == "dm" and cid_cur == self.chat_id("dm", sender if sender != self.username else to)) or \
                       (kind == "room" and cid_cur == self.chat_id("room", to)):
                        self.typing_lbl.configure(text=f"{sender} đang nhập..."); self.after(1200, lambda: self.typing_lbl.configure(text=""))
                return
            if kind == "dm":
                partner = sender if sender != self.username else to
                cid = self.chat_id("dm", partner)
            else:
                cid = self.chat_id("room", str(to))
            lst = self.history.setdefault(cid, [])
            lst.append(m)
            if not self.current_chat or self.chat_id(*self.current_chat) != cid:
                self.unread[cid] = self.unread.get(cid, 0) + 1
                self.refresh_lists()
            else:
                self.render_messages(cid)
            return

        if t == "fetch_history":
            if obj.get("ok") and self.current_chat:
                cid = self.chat_id(*self.current_chat)
                self.history[cid] = obj.get("messages", [])
                self.render_messages(cid)
            return

        if t == "search_users":
            res = obj.get("results", [])
            top = tk.Toplevel(self); top.title("Kết quả tìm kiếm (theo ID)")
            lb = tk.Listbox(top, width=40, height=12); lb.pack(padx=8, pady=8)
            self.search_index = []
            for it in res:
                if isinstance(it, dict):
                    uid = it.get("username")
                    if uid and uid != self.username:
                        name = it.get("full_name") or it.get("name") or ""
                        text = f"{name} — {uid}" if name else uid
                        lb.insert("end", text)
                        self.search_index.append(uid)
                else:
                    uid = str(it)
                    if uid != self.username:
                        lb.insert("end", uid)
                        self.search_index.append(uid)
            ttk.Button(top, text="Gửi lời mời", command=lambda: self._req_from_search(lb, top)).pack(pady=6)
            return

    def _req_from_search(self, lb, top):
        sel = lb.curselection()
        if not sel: return
        idx = sel[0]
        if idx < 0 or idx >= len(self.search_index): return
        uid = self.search_index[idx]
        self.net.send("friend_request", {"to": uid})
        top.destroy()

# --------------- run ---------------
if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
