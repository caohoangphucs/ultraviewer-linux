# UltraViewer Linux Controller (Reconstructed)

Dự án nghiên cứu và tái tạo bộ điều khiển **UltraViewer** độc lập cho môi trường Linux (Ubuntu / Debian / Arch / Fedora), cho phép kết nối và điều khiển máy tính Windows từ xa mà không cần cài đặt Wine hay phần mềm Windows gốc.

Repository cung cấp cả hai phương thức sử dụng:
1. **Native Desktop Application:** Chạy trực tiếp dưới dạng một cửa sổ phần mềm máy tính độc lập (GTK3 + WebKitGTK).
2. **Web Portal Service:** Host backend điều khiển trực tiếp qua trình duyệt web trên bất kỳ thiết bị nào (điện thoại, máy tính bảng, máy tính khác).

---

## 1. Yêu cầu Hệ thống & Môi trường

### Hệ điều hành
- Linux x86_64 (Ubuntu 20.04+, Debian 11+, Arch Linux, Fedora...)
- Python: `3.10` trở lên

### Cài đặt gói hệ thống (System Packages)
Trên **Ubuntu / Debian**:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libzstd1 gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

Trên **Arch Linux**:
```bash
sudo pacman -S python zstd gtk3 webkit2gtk-4.1
```

Trên **Fedora**:
```bash
sudo dnf install -y python3 zstd-devel gtk3 webkit2gtk4.1
```

---

## 2. Cài đặt Dependencies

Khởi tạo môi trường ảo Python và cài đặt các thư viện cần thiết:

```bash
git clone https://github.com/caohoangphucs/ultraviewer-linux.git
cd ultraviewer-linux

# Tạo và kích hoạt virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Cài đặt thư viện Python (Pillow, cryptography, PyGObject)
pip install -r requirements.txt
```

---

## 3. Hướng dẫn Khởi chạy

### Cách 1: Chạy Desktop App (Cửa sổ ứng dụng độc lập - Khuyên dùng)
Chạy trực tiếp bằng script 1-click:
```bash
./run.sh
```
Hoặc qua lệnh Python:
```bash
python3 app.py
```
- Cửa sổ phần mềm **UltraViewer Linux** sẽ mở lên ngay lập tức.
- Nhập **Partner ID** và **Password** của máy Windows cần điều khiển vào thanh công cụ bên trên.
- Nhấn **Kết nối** và click chuột vào khung màn hình để bắt đầu thao tác.

### Cách 2: Chạy Web Portal (Điều khiển qua trình duyệt)
Nếu bạn muốn host dịch vụ trên máy chủ (hoặc VPS) để điều khiển qua trình duyệt:
```bash
python3 server.py --port 8499 --host 0.0.0.0
```
- Mở trình duyệt và truy cập: `http://localhost:8499` (hoặc domain/IP máy chủ của bạn).
- Nhập Partner ID, Password và bấm Kết nối.

---

## 4. Cấu trúc Thư mục

- `app.py`: Bộ khởi chạy chính kết hợp backend controller và cửa sổ Native GUI.
- `app_window.py`: Cửa sổ Desktop GUI sử dụng GTK3 và WebKitGTK.
- `server.py`: HTTP Web Server xử lý API kết nối và streaming khung hình qua Web Portal.
- `viewer.html`: Giao diện Web Portal canvas nhận tương tác chuột và phím.
- `control_session.py`: Quản lý vòng đời phiên kết nối UltraViewer (Handshake, xác thực, điều hướng gói tin).
- `screen_decode.py`: Bộ giải mã khung hình thời gian thực (Zstandard RGB555 và JPEG Atlas).
- `input_control.py`: Mã hóa sự kiện chuột (di chuyển, click trái/phải, con lăn) và bàn phím (virtual-key codes).
- `8bit.dat`: Từ điển giải nén giao thức Zstandard gốc.
- `run.sh`: Script 1-click tự nhận diện môi trường và khởi chạy app.

---

## 5. Tuyên bố miễn trừ trách nhiệm (Disclaimer & Fair Use)

- **Mục đích nghiên cứu:** Dự án này được phát triển hoàn toàn phục vụ mục đích nghiên cứu học thuật, giáo dục và tăng cường khả năng tương tác liên nền tảng (Interoperability) theo nguyên tắc *Fair Use*.
- **Quyền sở hữu trí tuệ:** "UltraViewer" và các nhãn hiệu liên quan là tài sản trí tuệ và thương hiệu đã đăng ký của chủ sở hữu tương ứng (DucFabulous Co., Ltd / UltraViewer). Dự án mã nguồn mở này hoàn toàn **độc lập**, **không liên kết**, **không được tài trợ** và **không được ủy quyền** bởi chủ sở hữu UltraViewer.
- **Không chịu trách nhiệm:** Tác giả không chịu trách nhiệm đối với bất kỳ hành vi lạm dụng, vi phạm Điều khoản Dịch vụ (ToS), tổn thất dữ liệu hoặc bất kỳ thiệt hại nào phát sinh trực tiếp hoặc gián tiếp từ việc sử dụng phần mềm này. Người dùng tự chịu mọi rủi ro khi sử dụng.
- **Tuân thủ bản quyền:** Mã nguồn trong dự án này được viết lại độc lập từ đầu (clean-room re-implementation). Nếu chủ sở hữu nhãn hiệu có bất kỳ thắc mắc hoặc yêu cầu nào liên quan đến tài sản trí tuệ, vui lòng mở Issue hoặc liên hệ để được hỗ trợ gỡ bỏ kịp thời.
