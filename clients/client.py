import socket
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext

HOST = '127.0.0.1'   # Địa chỉ server (localhost)
PORT = 12345         # Cổng kết nối server

class ChatClient:
    def __init__(self, master):
        self.master = master
        self.master.title("Client Chat")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((HOST, PORT))
        except:
            messagebox.showerror("Lỗi", "Không thể kết nối đến server.")
            exit()

        self.username = ""
        self.current_room = None

        self.login_window()

    def login_window(self):
        self.clear_widgets()

        tk.Label(self.master, text="Đăng nhập", font=('Arial', 16)).pack(pady=10)
        tk.Label(self.master, text="Username:").pack()
        self.entry_username = tk.Entry(self.master)
        self.entry_username.pack()

        tk.Label(self.master, text="Password:").pack()
        self.entry_password = tk.Entry(self.master, show="*")
        self.entry_password.pack()

        tk.Button(self.master, text="Đăng nhập", command=self.login).pack(pady=5)
        tk.Button(self.master, text="Đăng ký", command=self.register).pack()

    def register(self):
        username = self.entry_username.get()
        password = self.entry_password.get()
        if not username or not password:
            messagebox.showwarning("Lỗi", "Không được để trống.")
            return

        self.sock.sendall(f"REGISTER|{username}|{password}".encode())
        response = self.sock.recv(1024).decode()
        if response == "REGISTER_SUCCESS":
            messagebox.showinfo("Thành công", "Đăng ký thành công.")
        else:
            messagebox.showerror("Lỗi", "Username đã tồn tại.")

    def login(self):
        username = self.entry_username.get()
        password = self.entry_password.get()
        if not username or not password:
            messagebox.showwarning("Lỗi", "Không được để trống.")
            return

        self.sock.sendall(f"LOGIN|{username}|{password}".encode())
        response = self.sock.recv(1024).decode()
        if response == "LOGIN_SUCCESS":
            self.username = username
            self.main_chat_window()
            threading.Thread(target=self.receive_messages, daemon=True).start()
        else:
            messagebox.showerror("Lỗi", "Sai thông tin đăng nhập.")

    def main_chat_window(self):
        self.clear_widgets()

        tk.Label(self.master, text=f"Xin chào, {self.username}", font=('Arial', 14)).pack(pady=5)

        self.text_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD, height=15)
        self.text_area.pack(padx=10, pady=5)
        self.text_area.config(state=tk.DISABLED)

        self.entry_msg = tk.Entry(self.master)
        self.entry_msg.pack(fill=tk.X, padx=10, pady=5)
        self.entry_msg.bind("<Return>", lambda event: self.send_message())

        frame_buttons = tk.Frame(self.master)
        frame_buttons.pack(pady=5)

        tk.Button(frame_buttons, text="Gửi", command=self.send_message).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_buttons, text="Tạo Phòng", command=self.create_room).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_buttons, text="Vào Phòng", command=self.join_room).pack(side=tk.LEFT, padx=5)

    def send_message(self):
        msg = self.entry_msg.get()
        if msg:
            self.sock.sendall(f"MSG|{self.current_room}|{msg}".encode())
            self.entry_msg.delete(0, tk.END)

    def create_room(self):
        room = simpledialog.askstring("Tạo phòng", "Nhập tên phòng:")
        if room:
            self.sock.sendall(f"CREATE_ROOM|{room}".encode())
            self.current_room = room
            self.show_info(f"Đã tạo và tham gia phòng: {room}")

    def join_room(self):
        room = simpledialog.askstring("Vào phòng", "Nhập tên phòng:")
        if room:
            self.sock.sendall(f"JOIN_ROOM|{room}".encode())
            self.current_room = room
            self.show_info(f"Đã tham gia phòng: {room}")

    def receive_messages(self):
        while True:
            try:
                data = self.sock.recv(4096).decode()
                if data:
                    self.show_info(data)
            except:
                break

    def show_info(self, msg):
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, msg + "\n")
        self.text_area.config(state=tk.DISABLED)
        self.text_area.see(tk.END)

    def clear_widgets(self):
        for widget in self.master.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    client_app = ChatClient(root)
    root.mainloop()
