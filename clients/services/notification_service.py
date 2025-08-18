
import tkinter as tk
from tkinter import messagebox

class Notifier:
    def __init__(self, root: tk.Tk):
        self.root = root

    def info(self, title: str, text: str):
        # Thông báo nhỏ gọn; có thể nâng cấp thành toast
        messagebox.showinfo(title, text, parent=self.root)