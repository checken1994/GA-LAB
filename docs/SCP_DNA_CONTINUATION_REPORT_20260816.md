# SCP DNA — Báo cáo tiếp tục xử lý sau audit P0/P1

**Ngày:** 16/08/2026
**PC:** `C:\Users\check\Downloads\scp\`
**Nguyên tắc:** Reality over Model; PASS chỉ có nghĩa là chưa thấy lỗi trong phạm vi đã kiểm tra.

## Kết luận hiện tại

SCP đã được sửa thêm ở ba vùng quan trọng: control plane cho capability/escalation, defensive response truthful, và evolution scheduler. Firewall Ollama trên PC cũng đã được người dùng chạy bằng quyền Administrator và chuyển từ **Public** sang **Private** ở cả hai rule.

SCP vẫn đang **tắt 24/7** đúng yêu cầu. Bốn port `3000`, `3030`, `8000`, `11434` đều đóng sau mỗi reality test. Hai Scheduled Task `SCP-247-Supervisor` và `SCP-247-Recovery-Watchdog` đều `Disabled`.

## Các thay đổi đã làm

| Commit | Thay đổi | Ý nghĩa |
|---|---|---|
| `e7dc89d` | Thêm `scp/api/routes/control_routes.py` và đăng ký vào `api_server.py` | Có route admin xác thực cho capability status/escalate/de-escalate và escalation status/approve/reject |
| `a4d55f0` | Sửa `scp/security/escalation.py` | Không còn ghi như thể đã chặn IP/process. Những action chưa có code thật trả `SKIPPED_NOT_IMPLEMENTED`; forensic logging mới trả `RECORDED`; có `enforcement_performed=false` |
| `f9ff5e6` | Nối evolution cycle vào deep-audit loop và đọc `SCP_EVOLUTION_AUTO` theo runtime | Khi cờ tắt, evolution trả trạng thái disabled. Khi cờ bật, chỉ chạy một cycle có giới hạn và vẫn qua test/rollback gate |

## Bằng chứng kiểm tra

| Kiểm tra | Kết quả |
|---|---:|
| Full pytest trên PC sau control plane | **101 passed, 2 warnings** |
| Full pytest trên PC sau defensive truth | **101 passed, 2 warnings** |
| Full pytest trên PC sau evolution wiring | **101 passed, 2 warnings** |
| Reality harness sau toàn bộ patch | **74/74 PASS, 0 FAIL, 0 TIMEOUT, 0 ERROR** |
| Control route không có token | **401**, không phải 200 |
| Control route có token hợp lệ trên backend thật | Capability status **200**, escalate **200**, de-escalate **200** |
| Escalation status khi judge chưa sẵn sàng | **503**, đúng fail-closed; sau khi judge ready trong poll tiếp theo là **200** |
| Package smoke cuối | Bốn port mở đúng; `health=200`; `CALL_CREATE=200`; control no-auth `401` |
| Sau khi dừng package | Bốn port đều đóng |
| Firewall Ollama | Hai rule `Enabled=True`, `Inbound`, `Allow`, **Profile=Private** |
| 24/7 | Supervisor **Disabled**, Recovery Watchdog **Disabled** |

## Giải thích điểm 503 của escalation

Lần gọi đầu tiên vào `/v105/escalation/status` có thể trả `503` trong lúc `RealityJudge` đang khởi tạo nền. Đây không phải route 404 và không phải mở cửa bỏ qua auth. Sau khi chờ thêm, cùng endpoint trả `200`. Đây là hành vi fail-closed đúng về bảo mật, nhưng trải nghiệm Dashboard vẫn nên hiển thị “SCP đang khởi động” thay vì báo lỗi chung.

## Package mới nhất

Binary backend runtime sau các patch có SHA-256:

`0A0341454FEAE37B661F9B06A9F2E5B0DF0941B9AC2CA3B4AC904C754186D59C`

Installer x64:

`F0FC3E717C2ACD2F013B7867E2D8FA1ECC2B487ED0346D85A61B8C3012F8E9D6`

Installer portable:

`BB99D273ED965F5A7DED297FFD9FB6271E8F6F61C1EB0BB0F0808FCB402BCD24`

Cả hai installer vẫn **NotSigned**. Đây là việc cần làm trước khi phát hành rộng vì Windows có thể hiện SmartScreen warning.

## Những phần vẫn chưa hoàn tất

### 1. Defensive action thật

SCP hiện đã trung thực hơn: nó không nói “đã block” khi chỉ ghi log. `block_ip`, `tighten_rate_limit`, `enable_honeypot` và `alert_cert` vẫn là policy intent hoặc log, chưa phải hành động OS/network thật. Đây là missing piece lớn nhất nếu mục tiêu là phản ứng tự động ngoài đời.

Không nên nối hành động tự động mạnh cho đến khi mỗi action có contract rõ: điều kiện kích hoạt, phạm vi, rollback, timeout, quyền Windows và reality test riêng.

### 2. Secret ACL

File production `.env` vẫn có quyền đọc cho nhóm `CodexSandboxUsers`. Tôi không sửa ACL vì không được tự ý thay nội dung hoặc quyền của production `.env` nếu chưa biết Manus Desktop cần quyền gì. Đây vẫn là P0 cần chủ máy quyết định sau khi có phương án rollback.

### 3. Cuộc gọi video qua mạng khác

WebRTC signaling đã có, nhưng source chưa có STUN/TURN. Chưa có bằng chứng hai PC ở hai mạng/NAT khác nhau truyền camera và mic ổn định. Hiện chỉ nên coi là signaling/API đã nối, chưa coi là cuộc gọi Internet hoàn chỉnh.

### 4. Camera/mic thật và PC thứ hai

Package smoke chứng minh backend, dashboard, call API và các port. Nó chưa chứng minh hai người dùng thật với hai webcam/mic nói chuyện hai chiều. Cũng chưa có bằng chứng cài installer trên một PC sạch hoàn toàn, cấp quyền camera/mic, migration data và rollback installer.

### 5. OTel

OpenTelemetry vẫn là đường tùy chọn. SDK chưa cài trong venv, chưa có OTLP collector và chưa có trace thật. Vì vậy chưa thể nói SCP có observability chuẩn OTel trong production.

### 6. Zalo, Telegram và TTS

Chưa có connector được kiểm chứng cho Zalo/Telegram; chưa có TTS để SCP nói lại bằng giọng nói. Nếu làm messaging từ xa, phải bổ sung xác thực webhook, chống replay, rate limit, command allowlist và human approval trước khi cho phép điều khiển máy.

### 7. Soak test

Chưa có chạy 24 giờ hoặc 7 ngày sau toàn bộ patch mới. Các vấn đề memory leak, log phình, SQLite lock và recovery sau mất mạng vẫn là câu hỏi mở.

## Vì sao chưa gọi là Production tuyệt đối

> **Một hệ thống pass test không đồng nghĩa hệ thống miễn nhiễm với mọi tấn công.**

Các test hiện tại có giá trị thật: chúng chứng minh import, route, auth, health, package startup, call API, shutdown và nhiều logic safety không lỗi trong điều kiện đã chạy. Nhưng chúng không chứng minh semantic correctness của mọi dự báo, không chứng minh camera/mic qua NAT, không chứng minh installer trên PC sạch, không chứng minh 7 ngày chạy nền, và không chứng minh defensive action ngoài hệ thống log.

## Thứ tự tiếp theo

Trước khi bật 24/7, cần ưu tiên ký installer, quyết định ACL `.env`, bổ sung STUN/TURN hoặc giới hạn rõ phạm vi cuộc gọi, rồi kiểm tra hai PC thật. Sau đó mới chạy soak 24 giờ rồi 7 ngày. OTel, messaging và TTS nên làm sau khi control plane và rollback đã ổn định.

## Tài liệu tham chiếu

[1] [OWASP Top 10 for Large Language Model Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[2] [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
[3] [OpenTelemetry Python FastAPI Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
