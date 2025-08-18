# Khung chính: tabs Friends / Rooms / Chats / Searchimport time
import time
import tkinter as tk
from tkinter import ttk, simpledialog
from typing import Dict

from services.notification_service import Notifier
from services.search_service import SearchService
from .chat_windows import ChatPanel
from .components import ScrollFrame, Badge

class MainWindow(ttk.Frame):
    def __init__(self, root, services: Dict[str, object], bus):
        super().__init__(root)
        self.root = root
        self.services = services
        self.bus = bus
        self.notif = Notifier(root)
        self.chats: Dict[str, ChatPanel] = {}

        self.pack(fill="both", expand=True)
        self._build_ui()
        self._wire_events()

    def _build_ui(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Friends tab
        self.friends_tab = ttk.Frame(self.nb)
        self.nb.add(self.friends_tab, text="Bạn bè")
        self.friends_list = ScrollFrame(self.friends_tab)
        self.friends_list.pack(fill="both", expand=True)

        # Rooms tab
        self.rooms_tab = ttk.Frame(self.nb)
        self.nb.add(self.rooms_tab, text="Phòng")
        top = ttk.Frame(self.rooms_tab)
        top.pack(fill="x")
        ttk.Button(top, text="Tạo phòng", command=self._create_room).pack(side="left", padx=4, pady=4)
        self.rooms_list = ScrollFrame(self.rooms_tab)
        self.rooms_list.pack(fill="both", expand=True)

        # Chats tab
        self.chats_tab = ttk.Frame(self.nb)
        self.nb.add(self.chats_tab, text="Chats")
        self.chat_holder = ttk.Frame(self.chats_tab)
        self.chat_holder.pack(fill="both", expand=True)

        # Search tab
        self.search_tab = ttk.Frame(self.nb)
        self.nb.add(self.search_tab, text="Tìm kiếm")
        self._build_search()

    def _build_search(self):
        s_top = ttk.Frame(self.search_tab)
        s_top.pack(fill="x", padx=6, pady=6)
        ttk.Label(s_top, text="Từ khóa").pack(side="left")
        self.search_entry = ttk.Entry(s_top, width=30)
        self.search_entry.pack(side="left", padx=6)
        ttk.Button(s_top, text="Tìm", command=self._search).pack(side="left")
        self.search_result = ScrollFrame(self.search_tab)
        self.search_result.pack(fill="both", expand=True)

    def _wire_events(self):
        bus = self.bus
        bus.subscribe("friends/list", self._on_friends_list)
        bus.subscribe("friends/update", self._on_friends_list)
        bus.subscribe("rooms/list", self._on_rooms_list)
        bus.subscribe("rooms/update", self._on_rooms_list)
        bus.subscribe("presence/update", self._on_presence)
        bus.subscribe("chat/message", self._on_message)
        bus.subscribe("chat/typing", self._on_typing)

    # ===== Friends =====
    def _on_friends_list(self, msg):
        # msg: {type: friends.list, friends:[{username, online}]}
        for child in self.friends_list.inner.winfo_children():
            child.destroy()
        for f in msg.get("friends", []):
            row = ttk.Frame(self.friends_list.inner)
            row.pack(fill="x", padx=6, pady=2)
            status = Badge(row, text=("online" if f.get("online") else "offline"), bg=("green" if f.get("online") else "gray"))
            status.pack(side="left")
            ttk.Label(row, text=f["username"]).pack(side="left", padx=8)
            ttk.Button(row, text="Chat", command=lambda u=f["username"]: self.open_chat("user", u)).pack(side="right")

    # ===== Rooms =====
    def _on_rooms_list(self, msg):
        for child in self.rooms_list.inner.winfo_children():
            child.destroy()
        for r in msg.get("rooms", []):
            row = ttk.Frame(self.rooms_list.inner)
            row.pack(fill="x", padx=6, pady=2)
            ttk.Label(row, text=f"{r['name']} ({r['id']})").pack(side="left")
            ttk.Button(row, text="Mở chat", command=lambda rid=r["id"]: self.open_chat("room", rid)).pack(side="right")

    def _create_room(self):
        name = simpledialog.askstring("Tạo phòng", "Tên phòng:", parent=self.root)
        if name:
            self.services["rooms"].create(name)

    # ===== Chat =====
    def open_chat(self, peer_type: str, peer_id: str):
        key = f"{peer_type}:{peer_id}"
        if key in self.chats:
            self.nb.select(self.chats[key])
            return
        panel = ChatPanel(self.chat_holder, self.services["msg"], peer_type, peer_id)
        self.chats[key] = panel
        self.nb.add(panel, text=f"{peer_id}")
        self.nb.select(panel)

    def _on_message(self, msg):
        key = f"{msg.get('peer_type')}:{msg.get('peer_id')}"
        panel = self.chats.get(key)
        if not panel:
            # mở tab mới khi có tin nhắn đến
            self.open_chat(msg.get('peer_type'), msg.get('peer_id'))
            panel = self.chats.get(key)
        if msg.get("type") == "message.image":
            from services.media import Media
            photo = Media.b64_to_photoimage(msg.get("b64") or msg.get("content"))
            panel.add_message(image_photo=photo, is_out=False)
        else:
            panel.add_message(text=msg.get("content", ""), is_out=False)
        self.notif.info("Tin nhắn mới", f"Từ {msg.get('from')} -> {msg.get('peer_id')}")

    def _on_typing(self, msg):
        key = f"{msg.get('peer_type')}:{msg.get('peer_id')}"
        panel = self.chats.get(key)
        if panel:
            panel.show_typing(msg.get("from"), msg.get("typing", False))

    def _on_presence(self, msg):
        # cập nhật danh sách bạn bè
        self.services["friends"].list()

    # ===== Search =====
    def _search(self):
        kw = self.search_entry.get().strip() or None
        rows = self.services["search"].search(None, None, kw, None)
        for c in self.search_result.inner.winfo_children():
            c.destroy()
        for peer_type, peer_id, direction, msg_type, content, ts in rows:
            row = ttk.Frame(self.search_result.inner)
            row.pack(fill="x", padx=6, pady=2)
            ts_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts/1000))
            ttk.Label(row, text=f"[{ts_s}] {peer_type}:{peer_id} {direction} {msg_type}").pack(side="left")
            if msg_type == "text":
                ttk.Label(row, text=content[:80]).pack(side="left", padx=6)
            ttk.Button(row, text="Mở", command=lambda pt=peer_type, pid=peer_id: self.open_chat(pt, pid)).pack(side="right")