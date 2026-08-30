# Hướng dẫn kết nối AI thủ công với SCP V3.1

## Nguyên tắc

SCP không nhận mật khẩu, mã OTP hoặc cookie của bạn qua tin nhắn. Bạn tự đăng nhập trong trình duyệt Edge/Chrome; SCP chỉ nhìn thấy các tab đã được mở qua DevTools cục bộ. SCP cũng không xử lý CAPTCHA và không gửi câu hỏi tới AI nếu request chưa có `approved=true`.

## Bước 1 — Mở phiên browser cho SCP

Đóng toàn bộ cửa sổ Edge/Chrome nếu chúng đang chạy. Trên Desktop, nhấp đúp **SCP Browser Session**. Lối tắt này chạy file `C:\Users\check\Downloads\scp\start-scp-browser.bat` và mở DevTools cục bộ ở cổng `9222`.

Nếu launcher báo đã có browser session đang nối với SCP, đó là trạng thái đúng và không cần mở thêm cửa sổ. Nếu launcher báo không tìm thấy browser, hãy chắc chắn rằng file BAT mới nhất đã được đồng bộ; máy Windows này dùng EdgeCore tại `C:\Program Files (x86)\Microsoft\EdgeCore\Optimized\msedge.exe`.

Có thể kiểm tra kết nối bằng PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/list | Select-Object title,url
```

## Bước 2 — Đăng nhập từng AI

Trong cùng cửa sổ browser, mở lần lượt các địa chỉ sau:

| Dịch vụ | URL cần mở | Hostname SCP nhận diện |
|---|---|---|
| ChatGPT | `https://chatgpt.com/` | `chatgpt.com` hoặc `chat.openai.com` |
| Claude | `https://claude.ai/` | `claude.ai` |
| Gemini | `https://gemini.google.com/` | `gemini.google.com` |

Bạn tự nhập email, mật khẩu, mã xác minh và CAPTCHA nếu dịch vụ yêu cầu. Sau khi đăng nhập, để mỗi dịch vụ ở một tab riêng và chờ giao diện chat hiện đầy đủ. Không cần gửi câu hỏi trong bước này.

## Bước 3 — Kiểm tra SCP đã nhìn thấy đúng tab

Mở dashboard SCP Desktop và xem khu vực **SCP có tay chân ở đâu?**. Web Navigator sẽ chuyển từ **Chưa nối browser** sang **Đã nối browser**. Trạng thái backend cũng có thể kiểm tra bằng:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v3/web/status
```

SCP chọn tab theo hostname. Vì vậy nó không gửi câu hỏi nhầm vào tab `about:blank`, tab tài liệu hoặc tab AI khác.

## Bước 4 — Chỉ thử gửi câu hỏi sau khi bạn đã kiểm tra tab

Khi bạn muốn cho SCP gửi một câu hỏi kiểm tra tới một AI, phải dùng approval rõ ràng. Ví dụ dưới đây chỉ là câu hỏi vô hại:

```powershell
$body = @{ ai = "chatgpt"; question = "Trả lời đúng một từ: OK"; approved = $true; useBrowser = $true; allowApiFallback = $false } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v3/ai/ask -Method Post -ContentType "application/json" -Body $body
```

Đổi `ai` thành `claude` hoặc `gemini` chỉ sau khi tab tương ứng đã đăng nhập. Nếu tab chưa có hostname đúng hoặc đang ở màn hình đăng nhập, SCP sẽ trả về lỗi “Open a logged-in … tab first” thay vì tự đăng nhập.

## Xử lý sự cố

Nếu dashboard báo browser đã nối nhưng AI Orchestrator không tìm thấy dịch vụ, hãy kiểm tra URL tab có đúng hostname hay không. Nếu Edge bị treo, đóng toàn bộ Edge rồi chạy lại **SCP Browser Session**. Nếu muốn dừng mọi hành động SCP ngay lập tức, dùng kill switch trước khi tiếp tục kiểm tra.
