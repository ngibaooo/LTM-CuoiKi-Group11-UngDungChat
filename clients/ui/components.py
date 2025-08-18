# Thành phần UI (message bubble, badges...)import tkinter as tk
from tkinter import ttk

class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0) # type: ignore
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0,0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas = canvas
        self._win = win

    def scroll_to_end(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

class Badge(ttk.Label):
    def __init__(self, parent, text, bg, fg="white"):
        super().__init__(parent, text=text, background=bg, foreground=fg, padding=(6,2))

class MessageBubble(ttk.Frame):
    def __init__(self, parent, text: str = "", image=None, is_out=False):
        super().__init__(parent)
        anchor = "e" if is_out else "w"
        self.columnconfigure(0, weight=1)
        holder = ttk.Frame(self)
        holder.grid(column=0, row=0, sticky=anchor, pady=4, padx=6)
        card = ttk.Frame(holder, padding=8, relief="solid", borderwidth=1)
        card.pack(anchor=anchor)
        if image is not None:
            lbl = ttk.Label(card, image=image)
            lbl.image = image
            lbl.pack()
        if text:
            ttk.Label(card, text=text, wraplength=420).pack()