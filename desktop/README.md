# SCP DNA Desktop Control Center

Ứng dụng này đóng gói hệ thống SCP hiện có thành một cửa sổ desktop Windows. Giao diện chính vẫn là dashboard Next.js; Electron quản lý vòng đời của bốn dịch vụ SCP, mở dashboard trong cửa sổ riêng và ghi log theo từng dịch vụ.

## Mô hình 1.6

Bản desktop được đánh dấu **SCP model version 1.6** qua tiêu đề cửa sổ, màn hình khởi động và biến môi trường `SCP_MODEL_VERSION=1.6`. Các lựa chọn model LLM hiện có trong `.env` của hệ thống SCP được giữ nguyên; ứng dụng không ghi đè API key hoặc model provider của bạn.

## Cài đặt lần đầu

Từ thư mục gốc `C:\Users\check\Downloads\scp`, chạy `install-scp.bat` nếu Python virtual environment hoặc các dependency của SCP chưa sẵn sàng. Sau đó, trong thư mục `desktop`, chạy:

```powershell
npm install
```

## Chạy

```powershell
npm start
```

Hoặc chạy `launch-scp-desktop.bat` từ thư mục gốc. Ứng dụng sẽ khởi động LLM bridge, loop scheduler, SCP Python API và dashboard Next.js; sau khi dashboard phản hồi, cửa sổ desktop sẽ hiện ra.

## Log và dừng dịch vụ

Log desktop nằm tại `data\desktop-logs`. Khi thoát cửa sổ, các tiến trình do ứng dụng tạo sẽ được dừng theo cây tiến trình Windows. Nếu cần dừng thủ công, chạy `stop-scp.bat` ở thư mục gốc.

## Ghi chú

Ứng dụng cần Bun, Node.js, Python virtual environment của SCP và file `.env` đã được cấu hình. Nếu dashboard không mở sau thời gian chờ, hãy kiểm tra các file log trong `data\desktop-logs` và cửa sổ terminal của các dịch vụ.

## SCP V3.1: PC Controller, Web Navigator và AI Orchestrator

SCP V3.1 ưu tiên phiên Chrome/Edge đã đăng nhập trên chính máy tính. Chạy `start-scp-browser.bat` một lần để mở profile browser riêng của SCP với DevTools cục bộ tại `http://127.0.0.1:9222/json/list`, sau đó đăng nhập thủ công vào các dịch vụ AI cần dùng. SCP không đọc mật khẩu, không xử lý CAPTCHA và không tự gửi câu hỏi nếu request chưa có `approved=true`.

PC Controller làm việc trên workspace SCP với capability level từ 0 đến 5. Level 0 chỉ đọc; build/test trong workspace cần level cao hơn và phê duyệt; mọi hành động được ghi vào `data\pc_controller\audit.jsonl`. Kill switch nằm tại `data\pc_controller\KILL_SWITCH` và có thể được kích hoạt để chặn ngay các hành động mới.

API kiểm tra trạng thái gồm `GET http://127.0.0.1:8000/v3/pc/status` và `GET http://127.0.0.1:8000/v3/web/status`. Web Navigator có thể đọc nguồn công khai qua `POST /v3/web/browse`; AI Orchestrator dùng `POST /v3/ai/ask` với `approved=true` khi cần điều khiển phiên browser đã đăng nhập. Cross-verification dùng `POST /v3/ai/cross-verify` và không xem sự đồng thuận của nhiều AI là bằng chứng cuối cùng.
