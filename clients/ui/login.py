# Màn hình Login / Registerimport tkinter as tk
from tkinter import ttk

class LoginFrame(ttk.Frame):
    def __init__(self, parent, on_login, on_register):
        super().__init__(parent, padding=16)
        self.on_login = on_login
        self.on_register = on_register

        ttk.Label(self, text="Tên đăng nhập").grid(row=0, column=0, sticky="w")
        self.username = ttk.Entry(self)
        self.username.grid(row=1, column=0, sticky="ew")

        ttk.Label(self, text="Mật khẩu").grid(row=2, column=0, sticky="w", pady=(8,0))
        self.password = ttk.Entry(self, show="*")
        self.password.grid(row=3, column=0, sticky="ew")

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, pady=12, sticky="ew")
        ttk.Button(btns, text="Đăng nhập", command=self._login).pack(side="left")
        ttk.Button(btns, text="Đăng ký", command=self._register).pack(side="left", padx=8)

        self.columnconfigure(0, weight=1)

    def _login(self):
        self.on_login(self.username.get().strip(), self.password.get().strip())

    def _register(self):
        self.on_register(self.username.get().strip(), self.password.get().strip())