
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from services.media import Media
from .components import ScrollFrame, MessageBubble
from utils.typing_timer import TypingTimer

class ChatPanel(ttk.Frame):
    def __init__(self, parent, messaging_service, peer_type: str, peer_id: str):
        super().__init__(parent)
        self.messaging = messaging_service
        self.peer_type = peer_type
        self.peer_id = peer_id
        self.photos = []  # giữ reference ảnh

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.view = ScrollFrame(self)
        self.view.grid(row=0, column=0, sticky="nsew")

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.entry = ttk.Entry(bar)
        self.entry.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.entry.bind("<KeyPress>", self._on_keypress)

        ttk.Button(bar, text="Gửi", command=self._send_text).grid(row=0, column=1, padx=4)
        ttk.Button(bar, text="Ảnh", command=self._send_image).grid(row=0, column=2)

        self.typing_lbl = ttk.Label(self, text="")
        self.typing_lbl.grid(row=2, column=0, sticky="w", padx=8)

        self.typing_timer = TypingTimer(lambda is_typing: self._typing_emit(is_typing))

    def add_message(self, text=None, image_photo=None, is_out=False):
        bubble = MessageBubble(self.view.inner, text=text or "", image=image_photo, is_out=is_out)
        bubble.pack(fill="x")
        if image_photo:
            self.photos.append(image_photo)
        self.view.scroll_to_end()

    def show_typing(self, who: str, is_typing: bool):
        self.typing_lbl.configure(text=f"{who} đang gõ..." if is_typing else "")

    def _send_text(self):
        content = self.entry.get().strip()
        if not content:
            return
        if self.peer_type == "user":
            self.messaging.send_text_to_user(self.peer_id, content)
        else:
            self.messaging.send_text_to_room(self.peer_id, content)
        self.add_message(text=content, is_out=True)
        self.entry.delete(0, tk.END)

    def _send_image(self):
        path = filedialog.askopenfilename(title="Chọn ảnh", filetypes=[("Image", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"), ("All", "*.*")])
        if not path:
            return
        b64, _ = Media.load_and_resize_to_b64(Path(path))
        if self.peer_type == "user":
            self.messaging.send_image_to_user(self.peer_id, b64)
        else:
            self.messaging.send_image_to_room(self.peer_id, b64)
        photo = Media.b64_to_photoimage(b64)
        self.add_message(image_photo=photo, is_out=True)

    def _on_keypress(self, _):
        self.typing_timer.user_pressed()

    def _typing_emit(self, is_typing: bool):
        if self.peer_type == "user":
            self.messaging.typing_to_user(self.peer_id, is_typing)
        else:
            self.messaging.typing_to_room(self.peer_id, is_typing)