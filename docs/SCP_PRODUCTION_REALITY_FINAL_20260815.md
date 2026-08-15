# SCP — Báo cáo kiểm chứng thực tế cuối phiên

**Ngày:** 15/08/2026
**PC kiểm tra:** Windows 11 của Minh, `C:\Users\check\Downloads\scp\`
**GitHub:** `https://github.com/checken1994/GA-LAB`
**Commit cuối:** `1bb7f678fc91f12cf973d14c15986e3248b17af6`

## 1. Kết luận ngắn

SCP đã có một **bản Desktop Release Candidate có thể đóng gói**, và bản unpacked cuối đã chạy thực tế trên PC: bốn dịch vụ mở đúng port, backend trả health 200, tạo phòng call trả 200, rồi toàn bộ tiến trình được dừng và bốn port đóng lại. Bộ reality harness hiện có cũng chạy **74/74 PASS, 0 FAIL, 0 TIMEOUT, 0 ERROR**.

Tuy nhiên, theo nguyên tắc **PASS không có nghĩa là đã chứng minh mọi thứ đúng**, SCP chưa nên được gọi là “Production hoàn toàn” cho mọi mục tiêu ban đầu. 24/7 đang **tắt đúng yêu cầu của Minh**; OTel mới là tích hợp tùy chọn, chưa có collector đang chạy; camera/mic đã có luồng code nhưng chưa có bằng chứng hai người dùng thật gọi video qua hai máy; Zalo/Telegram chưa nối; constitution chưa có dòng xác nhận con người. Vì vậy trạng thái đúng là: **Desktop Release Candidate đã được kiểm chứng phần khởi động/đóng gói; hệ thống AI phòng thủ tổng thể vẫn còn các giới hạn phải nói rõ bên dưới**.

## 2. Những việc đã sửa trong phiên này

| Khu vực | Thay đổi | Ý nghĩa thực tế |
|---|---|---|
| WebRTC call | Thêm CallSessionHub, API tạo phòng/trạng thái, WebSocket relay offer/answer/ICE, giới hạn 2 người và TTL ngắn | Có đường truyền tín hiệu để hai trình duyệt thương lượng cuộc gọi; SCP không lưu audio/video |
| Desktop UI | Thêm VideoCallPanel, tạo/vào phòng, camera/mic chỉ bật sau khi người dùng bấm, avatar dự phòng | Giao diện đã có khung cuộc gọi và không tự bật camera/mic |
| Electron CSP | Cho phép `ws://127.0.0.1:8000` và `ws://localhost:8000` trong production CSP | WebRTC signaling không bị chính CSP của Desktop chặn |
| API thiếu trong clean checkout | Đưa `evidence_filter.py` và `batch_benchmark_routes.py` vào GitHub | Clone sạch không còn thiếu hai file làm import/judge/Hands bị gãy |
| External trust | Sửa cách tìm anchor để chạy đúng khi khởi động từ repo root hoặc trong package `scp` | Không còn cảnh báo giả rằng external audit files bị mất chỉ vì sai current directory |
| OTel | Thêm tích hợp `scp/observability/otel.py` và `scp/requirements-otel.txt` | Có thể bật trace FastAPI khi chủ động cấu hình OTLP; mặc định vẫn tắt, không gửi dữ liệu tự ý |
| Packaging | `build_runtime.ps1` giờ bắt buộc copy `dashboard/server.js`; manifest ghi rõ dashboard là runtime bắt buộc | PC thứ hai không chỉ có exe backend mà còn có Dashboard để Electron mở được |
| Backend runtime | Phát hiện bản exe cũ lỗi `Failed to extract MSVCP140_ATOMIC_WAIT.dll`; rebuild PyInstaller với `upx=False` | Bản backend mới không còn lỗi extract DLL trong probe trực tiếp |

## 3. Bằng chứng chạy trên PC thật

### 3.1. Source và backend

Các file Python đã compile thành công trên PC thật gồm call hub, call routes, batch benchmark routes, external trust, OTel và `api_server.py`. Backend source chạy qua Uvicorn đã trả `health=200`, `POST /v3/call/sessions=200`, `GET /v3/call/status=200`, và `GET /v3/hands/status=200`.

Bản PyInstaller mới được build lại khi bản cũ bị phát hiện lỗi. Probe trực tiếp bản mới cho kết quả `HEALTH=200` và `CALL_CREATE=200`; log không còn chuỗi `Failed to extract` hoặc `MSVCP140_ATOMIC_WAIT.dll`. Bản mới được chép vào `desktop\runtime\scp-backend.exe`, có backup rollback trong `.private-secrets\runtime-backup-before-backend-rebuild-20260815-195420\scp-backend.exe`.

### 3.2. Desktop package cuối

Electron Builder đã tạo hai file trên PC thật:

| File | Kích thước | SHA-256 | Chữ ký |
|---|---:|---|---|
| `desktop\release\SCP-DNA-Control-Center-1.6.0-x64.exe` | 686,363,387 bytes | `355E99AA9996FCD116524175B4E3B938589D29C487FAA15DC261CF6F7A35DE81` | `NotSigned` |
| `desktop\release\SCP-DNA-Control-Center-1.6.0-portable.exe` | 686,133,361 bytes | `4E46D4DC0F38591F3001565705F54E5846822B01C02E046E6E6D7B891CE07E3E` | `NotSigned` |

Bản unpacked được chạy lại sau lần build cuối và chờ đủ thời gian. Kết quả là `PORT_3000=True`, `PORT_3030=True`, `PORT_8000=True`, `PORT_11434=True`, `HEALTH=200`, `CALL_CREATE=200`. Sau khi dừng app, bốn port đều trở về `False`. Không còn tiến trình `scp-backend`, `scp-llm-bridge`, `scp-loop-scheduler` hoặc `scp-autofix-worker` chạy.

### 3.3. Reality harness

Harness có sẵn trong repo đã chạy trên PC thật và cho kết quả:

| Chỉ số | Kết quả |
|---|---:|
| Tổng bài | 74 |
| PASS | 74 |
| FAIL | 0 |
| TIMEOUT | 0 |
| ERROR | 0 |

Đây là bằng chứng tốt cho phạm vi mà harness đang kiểm tra. Nó **không** chứng minh được camera/mic của người dùng, cuộc gọi giữa hai máy, Zalo/Telegram, OTel collector, hoặc soak 24/7 nhiều ngày.

## 4. Trạng thái 24/7 và an toàn sau kiểm tra

Theo yêu cầu của Minh, hai Scheduled Task vẫn tắt:

| Scheduled Task | Trạng thái cuối |
|---|---|
| `SCP-247-Supervisor` | `Disabled` |
| `SCP-247-Recovery-Watchdog` | `Disabled` |

Sau smoke test cuối, các port `3000`, `3030`, `8000`, `11434` đều đóng. File `.env` production ở `C:\Users\check\Downloads\.env` không bị sửa. Các secret thật không được in ra màn hình. Một số thư mục build cũ rất lớn đã được xóa có chọn lọc trong vùng `.private-secrets` để giải phóng ổ đĩa; inventory trước khi dọn nằm tại `C:\Users\check\Downloads\scp\.private-secrets\cleanup-inventory-20260815.json`. Data SCP, runtime hiện tại, production ENV và backup rollback mới nhất không bị xóa.

## 5. Các giới hạn còn lại — nói thẳng

| Khoảng trống | Đã chứng minh đến đâu | Vì sao chưa gọi là hoàn tất |
|---|---|---|
| Camera/mic | Dashboard có `getUserMedia`, MediaRecorder, capture ảnh và voice route; permission Electron đã sửa | Chưa có phiên kiểm tra hai người dùng thật trên hai browser/máy có webcam/mic thật |
| Video call | Backend signaling tạo phòng, giới hạn peer và relay message đã có; API HTTP package pass | Chưa chứng minh media stream đi xuyên suốt giữa hai máy; signaling không phải bản thân audio/video |
| OTel | Code tích hợp tùy chọn, dependency profile riêng, không thu header/body | PC chưa cài SDK và chưa có OTLP collector nên trace thật chưa được xuất |
| Human constitution approval | External audit files và CI directory được tìm thấy đúng | `constitution.py` chưa có marker nghiêm ngặt `# HUMAN_APPROVED_BY: <name> <YYYY-MM-DD>`; không được tự thêm thay cho con người |
| 24/7 | Supervisor và watchdog vẫn tồn tại, XML rollback còn | Đang disabled theo yêu cầu; chưa chạy soak test 24 giờ sau các patch mới |
| Benchmark AI | Kết quả trước đó: factual-only `0.3`, self-correction `0`, verifier consistency `0.5`, security `0.6` | Điểm này cho thấy chất lượng AI và tự sửa còn yếu; 74 reality PASS không xóa được kết quả benchmark |
| External messaging | Chưa có đường Zalo/Telegram production | Chưa có connector, xác thực, chống replay và policy gửi lệnh ra ngoài |
| Code signing | Installer đã build được nhưng `Authenticode=NotSigned` | PC khác có thể hiện cảnh báo Windows SmartScreen; muốn phát hành rộng cần certificate ký mã |

## 6. Bài học từ hệ thống bên ngoài đã đưa vào

OWASP GenAI Security Project hiện coi prompt injection, output không an toàn, poisoning, denial of service, supply chain, rò rỉ thông tin, plugin không an toàn, excessive agency, overreliance và model theft là các nhóm rủi ro riêng [1]. Vì vậy SCP không nên dùng một cờ “security PASS” để đại diện cho tất cả các nhóm.

NIST AI RMF nhấn mạnh việc đưa yếu tố tin cậy vào thiết kế, phát triển, sử dụng và đánh giá AI [2]. Cách áp dụng vào SCP là tách bằng chứng: policy, ledger, benchmark, approval và external anchor phải cho thấy từng việc đã được kiểm tra đến đâu.

Tài liệu OpenTelemetry cho FastAPI hướng dẫn instrument request và cho phép loại trừ health/metrics, đồng thời cảnh báo việc thu header phải sanitize để không lưu PII, cookie hoặc session key [3]. Patch OTel của SCP làm theo hướng an toàn này: mặc định tắt, cần endpoint rõ ràng mới bật, không thu body/query/header mặc định và có danh sách sanitize.

## 7. Các commit đã đồng bộ GitHub

| Commit | Nội dung |
|---|---|
| `04487e2` | WebRTC signaling bounded và Desktop video panel |
| `52c645c` | Đưa evidence filter bắt buộc vào repo |
| `d764ad0` | Sửa resolve external trust từ repo root/package root |
| `c58765d` | Đưa batch benchmark route vào repo |
| `b9cb7af` | Sửa resolve baseline hash external trust |
| `36fb96b` | Cho phép local WebRTC WebSocket trong Electron production CSP |
| `2b6b689` | Packaging bắt buộc có Dashboard standalone |
| `1bb7f67` | OTel FastAPI tracing tùy chọn, mặc định tắt |

## 8. Kết luận sử dụng

Minh có thể dùng hai file installer trong thư mục `C:\Users\check\Downloads\scp\desktop\release\`. Nếu chỉ muốn chạy thử trên PC khác, bản portable là cách ít bước hơn. Nếu muốn cài như ứng dụng Windows, dùng bản `x64.exe`. Vì file chưa ký chứng thư, Windows có thể hiện cảnh báo; đó là cảnh báo nguồn phát hành, không phải bằng chứng rằng file bị nhiễm mã độc.

SCP hiện đã vượt qua bước quan trọng: **code sạch đã đồng bộ, backend packaged cũ đã bị phát hiện và thay thế, Dashboard đã nằm trong package, call API đã chạy thật, và 24/7 không bị bật ngoài ý muốn**. Nhưng SCP vẫn chưa đạt tuyên bố “bắt được tất cả tấn công AI + con người”. Muốn đạt mức đó phải tiếp tục chứng minh bằng benchmark độc lập, kiểm tra hai máy có webcam/mic thật, soak 24/7, OTel collector, messaging có xác thực và ký mã Windows.

## Tài liệu tham chiếu

[1] [OWASP GenAI/LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[2] [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
[3] [OpenTelemetry FastAPI Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
