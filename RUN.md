# Điều khiển UltraViewer trên Windows từ Linux

Bản phục hồi giao thức bằng Python, đã thử trực tiếp với Windows10 VM104/UltraViewer6.6.124. Giao diện chạy cục bộ trong trình duyệt; kết nối và giải mã chạy trên Linux.

## Cài và chạy

Yêu cầu Python3.10 trở lên, thư viện hệ thống libzstd, các gói trong requirements.txt.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python viewer.py /path/registration-private.json /path/partner-private.json --dictionary 8bit.dat --original-certificate-policy --port 0
```

Mở URL127.0.0.1 được in ra, bấm Kết nối, click màn hình để điều khiển. Nút Ngắt kết nối đóng phiên; bấm Kết nối để nối lại. Ctrl+C dừng viewer. Cờ --help hoặc help hiển thị hướng dẫn.

Trên máy đã kiểm thử, hai hồ sơ riêng đang ở:

- `./linux-controller-private.json`
- `./default-partner.json`

Thay hai đường dẫn `/path` trong lệnh bằng các đường dẫn này. Hồ sơ đăng ký gồm `ansi_codec` và 26 terms; hồ sơ đối tác gồm 17 terms, password, password_type. `viewer` giữ các hồ sơ ở phía máy chủ, không đưa mật khẩu vào HTML.

## Kiểm tra

```sh
.venv/bin/python -m unittest discover -s . -q
```

Đã quan sát Windows nhận chuột trái/phải, bàn phím và phím bổ trợ, mở Notepad và nhập văn bản, cuộn Edge hai chiều. Giao diện thật đã ngắt/kết nối lại rồi tiếp tục gửi Ctrl+End. Bằng chứng đi kèm trong thư mục outputs của phiên làm việc.

## Giới hạn

Mặc định1024x768, RGB555, JPEGblock32 khớp máy thử; có thể chỉnh --width/--height/--block-size. Chưa tự thương lượng mọi độ phân giải/định dạng. Gói ảnhfield5 chưa được hỗ trợ; gặp dạng ảnh chưa hiểu sẽ dừng và báo lỗi, không bỏ qua dữ liệu. Một số phím tắt bị trình duyệt giữ lại. Chưa triển khai âm thanh, truyền file, clipboard hay phía máy được điều khiển.

--original-certificate-policy khớp chương trình gốc nhưng không xác thực chứng chỉ máy chủ. Không có cờ này, dùng xác thực TLS tiêu chuẩn; chưa chứng minh hoạt động với hạ tầng hiện tại. Viewer chỉ lắng nghe loopback, có token và kiểm tra Origin cho lệnh điều khiển.

8bit.dat được lấy từ bản UltraViewer người dùng cung cấp, SHA256 9aa45789d9ff9d329a623a685d57b67e33c777019de9ce1f273f21860e4bfe6b. Đây là bộ từ điển giải nén của định dạng đã thử.

Kiểm thử ổn định cuối:120.03giây,48thao tác,75frames,không lỗi,worker dừng sạch. Gói giao được chạy hai vòng kết nối/nhận ảnh/ngắt thành công.38tests đạt.
