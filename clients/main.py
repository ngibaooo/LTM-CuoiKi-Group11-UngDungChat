
import socket
import threading
from config import SERVER_HOST, SERVER_PORT, BUFFER_SIZE, ENCODING
from auth import login, register

def client_program():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((SERVER_HOST, SERVER_PORT))
    except:
        print(" Không thể kết nối đến server!")
        return

    print(" Đã kết nối đến server.")

    while True:
        print("\n1. Đăng nhập\n2. Đăng ký\n3. Thoát")
        choice = input("Chọn chức năng: ")
        if choice == '1':
            if login(client_socket):
                break
        elif choice == '2':
            register(client_socket)
        elif choice == '3':
            client_socket.close()
            return
        else:
            print(" Lựa chọn không hợp lệ.")

    # TODO: Hiện tại chỉ kết nối - chưa có chat
    print(" Đăng nhập thành công. Đang chuẩn bị vào hệ thống chat...")

if __name__ == '__main__':
    client_program()

