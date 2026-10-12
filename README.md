# UltraViewer Linux Controller (Reconstructed)

Dự án tái tạo bộ điều khiển UltraViewer chạy độc lập trên môi trường Linux (Ubuntu/Debian), bao gồm cả giao diện Web Portal và Native Desktop Application.

## Tính năng
- **Kết nối UltraViewer chuẩn giao thức:** Đăng ký và kết nối điều khiển Windows UltraViewer qua Relay server.
- **Giải mã màn hình Realtime:** Hỗ trợ Zstandard dictionary decode (RGB555) và JPEG Atlas buffer.
- **Tương tác chuột & bàn phím:** Gửi sự kiện click, kéo, cuộn chuột và phím điều khiển từ xa.
- **Giao diện đa nền tảng:**
  - **Web Portal:** Host dịch vụ web điều khiển trực tiếp trên trình duyệt qua WebSocket/HTTP (`server.py`).
  - **Native Desktop App:** Cửa sổ ứng dụng máy tính độc lập sử dụng GTK3 + WebKitGTK (`app.py`).

## Hướng dẫn cài đặt & Chạy

### Yêu cầu hệ thống
- Linux (x86_64)
- Python 3.10+
- Thư viện C: `libzstd`
- Thư viện GUI (cho Native App): `gir1.2-webkit2-4.1`, `gir1.2-gtk-3.0`

### Cài đặt dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Chạy Desktop Application (Native Window)
```bash
./run.sh
```
Nhập **Partner ID** và **Password** trên cửa sổ ứng dụng và nhấn **Kết nối**.

### 2. Chạy Web Portal Server (Trình duyệt)
```bash
python3 server.py --port 8499 --host 0.0.0.0
```
Truy cập `http://localhost:8499` từ trình duyệt bất kỳ.
