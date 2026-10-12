# Hoàn tất mục tiêu điều khiển Windows — R227

Phạm vi theo yêu cầu đổi mục tiêu của người dùng: kết nối và điều khiển Windows chạy UltraViewer từ Linux; không phải phục hồi toàn bộ phần mềm.

|Tiêu chí|Bằng chứng kiểm chứng|
|---|---|
|REA/Ghidra phục vụ phục hồi|Các evidence REA/Ghidra và phân tích ABI/native/managed được lưu trong báo cáo remote-screen/network-dispatch; mã phục hồi nối những đường đã quan sát.|
|Chạy mã Linux đã giao|Gói UltraViewer-Linux-controller đã chạy38 tests; packaged-viewer-live-evidence.json ghi hai vòng chạy từ chính thư mục giao, nhận màn hình và ngắt worker sạch.|
|Xác thực máy Windows được phép|Command8/status1, login acknowledgement6.6.124, màn hình thật và tác động input quan sát được. Không suy ra xác thực chỉ từ login ack.|
|Màn hình cập nhật liên tục|sustained-live-evidence.json:120.03giây,75frames, không lỗi; ảnh1024x768 được mở kiểm tra.|
|Chuột/phím/phím bổ trợ|Notepad hiển thị uv linux ok, right-click menu; Edge cuộn lên/xuống. Giao diện canvas Ctrl+Home và Ctrl+End có tác động quan sát bằng ảnh.|
|Ngắt và nối lại, điều khiển tiếp|Browser UI chuyển disconnected, nối lại rồi Ctrl+End làm Edge tới footer; hai vòng HTTP từ gói giao đều dừng worker.|
|Tài liệu/bằng chứng/mã nguồn|RUN.md, MANIFEST.json, source và8bit.dat trong ZIP; mật khẩu/hồ sơ riêng không đưa vào gói.|

Thử ổn định có giới hạn120giây,48thao tác, không phải đảm bảo hoạt động mọi phiên hoặc hàng giờ. Field5, thương lượng mọi độ phân giải/định dạng, phím tắt trình duyệt giữ lại, TLS original-certificate-policy và các tính năng chưa triển khai được ghi rõ trong RUN.md. Chúng không được tuyên bố đã phục hồi. Hồ sơ đang dùng được giữ riêng trên máy thử; gói không có trình tạo hồ sơ cho máy mới.

38 kiểm thử đạt. Offline UI khi tiến trình thử dừng hiển thị Không liên lạc được viewer. Các tab và phiên thử đã đóng; không để kết nối điều khiển Windows chạy nền.
