     # Xem ảnh nhận/gửiimport tkinter as tk
from tkinter import ttk

class ImagePreview(tk.Toplevel): # type: ignore
    def __init__(self, master, photo):
        super().__init__(master)
        self.title("Xem ảnh")
        lbl = ttk.Label(self, image=photo)
        lbl.image = photo
        lbl.pack(padx=8, pady=8)