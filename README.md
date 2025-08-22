# Ứng Dụng Chat (Client - Server)

---

## 📌 Giới thiệu
Ứng dụng chat này được xây dựng dựa trên mô hình **Client - Server**, cho phép nhiều người dùng kết nối và trò chuyện với nhau theo thời gian thực.  
Ứng dụng sử dụng **socket** để truyền dữ liệu qua mạng.  

---

## 👥 Thành viên nhóm
| Họ tên           | MSSV         | Vai trò          |
|------------------|--------------|------------------|
| Nguyễn Hữu Hoàng | 067205000461 | Xử lý Server |
| Ngô Gia Bảo | 079205011307            | Xử lý Database     |
| Đỗ Thanh Tiến | 052205004180 | Xử lý Client    |
| Mai Đại Trí | 080205001449 | Tester và docs        |

---

## ✨ Tính năng nổi bật
- Chat nhiều người dùng cùng lúc (multi-client).
- Broadcast tin nhắn theo thời gian thực.
- Đặt **tên hiển thị (username)** khi tham gia chat.
- Cấu trúc rõ ràng, dễ mở rộng.

---

## ⚙️ Công nghệ sử dụng
- Ngôn ngữ: `Python`
- Socket TCP/UDP
- Giao thức mạng cơ bản

---

## 📝 Luật hoạt động
1. **Server** cần chạy trước để lắng nghe các kết nối.
2. **Client** có thể kết nối đến server bằng địa chỉ IP và cổng.
3. Khi một client gửi tin nhắn, server sẽ nhận và phân phối lại cho tất cả các client khác (broadcast).
4. Mỗi người dùng sẽ nhập **tên hiển thị (username)** khi tham gia.