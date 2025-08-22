# Chat Application (Socket + Python + MySQL)

---

## 📌 Giới thiệu
Ứng dụng chat real-time viết bằng Python + Tkinter.
Client kết nối đến server qua TCP socket, sử dụng JSON protocol để giao tiếp.
Hỗ trợ chat nhóm (Rooms), chat riêng (Direct Message), quản lý bạn bè và trạng thái online/offline.  

---

## 👥 Thành viên nhóm
| Họ tên           | MSSV         | Vai trò          |
|------------------|--------------|------------------|
| Nguyễn Hữu Hoàng | 067205000461 | Xử lý Server |
| Ngô Gia Bảo | 079205011307            | Xử lý Database     |
| Đỗ Thanh Tiến | 052205004180 | Xử lý Client    |
| Mai Đại Trí | 080205001449 | Tester và docs        |

---

## ✨ Tính năng
- Đăng ký / Đăng nhập tài khoản.
      - Chat nhóm trong các phòng (Rooms).
      - Chat riêng (DM) giữa hai người.
      - Quản lý bạn bè:
          + Gửi/nhận lời mời kết bạn.
          + Chấp nhận yêu cầu.
          + Danh sách bạn bè kèm trạng thái online/offline.
      - Hiển thị tin nhắn chưa đọc (unread counter).
      - Lưu tin nhắn tạm (buffer) để chuyển đổi nhanh giữa các cuộc trò chuyện.
      - UI thân thiện với Tkinter + Notebook tabs:
          + Tab Chat (phòng & bạn bè).
          + Tab Phòng.
          + Tab Bạn bè.

Thông báo kết quả từ server bằng popup.

---

## 📦 Yêu cầu hệ thống
- Python 3.9+
- MySQL
- Các thư viện Python:
    + socket
    + threading
    + queue
    + json
    + tkinter
    + contextlib
## 🚀 Cách sử dụng
- Đăng ký tài khoản: Nhập tên hiển thị, username, password, email → nhấn Đăng ký.
- Đăng nhập: Nhập username & password → nhấn Đăng nhập.
- Sau khi đăng nhập thành công:
    + Chat nhóm: chọn phòng từ danh sách hoặc tham gia phòng mới.
    + Chat riêng: chọn bạn bè từ danh sách bên trái.
- Kết bạn: gửi lời mời theo tên hiển thị.
- Chấp nhận bạn bè: chọn từ danh sách yêu cầu.
- Đăng xuất: bấm nút ở góc trên bên phải.
## 🚀 Cách chạy
1. Khởi động server:
python server.py
//Mặc định chạy ở 0.0.0.0:5000.

2. Chạy client:
python client.py
//Client sẽ kết nối tới server qua TCP socket.

## 📌 Ghi chú
- Cần chạy server trước khi mở client.
- Đây là bản demo học tập, chưa tối ưu bảo mật.
- Có thể mở rộng thêm:
    + Gửi file, ảnh.
    + Thông báo desktop.