# SCP — Audit các thiếu sót còn lại sau Release Candidate

**Ngày kiểm tra:** 15/08/2026
**Máy:** Windows 11 của Minh, `C:\Users\check\Downloads\scp\`
**Commit source cuối:** `d33f00d` — `fix(security): fail closed for non-loopback production binds`

## Kết luận ngắn

SCP đã ổn hơn bản trước và không còn lỗi khởi động rõ ràng trong phạm vi đã kiểm tra. Sau bản vá mới, full pytest đạt **101 passed, 2 warnings**, reality harness đạt **74/74 PASS, 0 FAIL, 0 TIMEOUT, 0 ERROR**, và bản Desktop unpacked cuối chạy thật với bốn port, `health=200`, tạo call `200`, call status `200`. Sau khi dừng, cả bốn port đều đóng. Hai Scheduled Task 24/7 vẫn Disabled đúng yêu cầu.

Nhưng vẫn còn các điểm quan trọng. Một số là **lỗ hổng cấu hình thật**, một số là **chức năng chưa nối**, một số là **chưa có bằng chứng ngoài thực tế mô phỏng**. Vì vậy SCP chưa nên được gọi là “bắt được tất cả tấn công AI + con người” hoặc “Production tuyệt đối”.

## 1. Vấn đề cần xử lý trước khi bật 24/7

| Mức | Vấn đề | Bằng chứng | Tác động |
|---|---|---|---|
| **P0** | Quyền đọc file `.env` quá rộng | ACL của `C:\Users\check\Downloads\.env` và `C:\Users\check\Downloads\scp\.env` có nhóm `Minh\CodexSandboxUsers` với quyền ReadAndExecute | Một chương trình chạy trong nhóm đó có thể đọc token/password nếu không có lớp cách ly khác. Đây không phải bằng chứng đã bị gửi ra ngoài, nhưng là cửa đọc secret thật |
| **P0** | Firewall có rule `ollama.exe` Allow trên profile Public | Rule inbound `ollama.exe` đang Enabled=True, Action=Allow, Profile=Public; Ollama hiện không chạy lúc kiểm tra | Nếu Ollama bind ra ngoài loopback trong tương lai, máy có thể nhận kết nối từ mạng Public. Không được xóa Ollama, nhưng phải giới hạn rule về Private/loopback hoặc tắt khi không dùng |
| **P0** | Cơ chế “phòng thủ phản công” chưa phải chặn thật | `execute_defensive_playbook()` trong `scp/security/escalation.py` xác thực tên action rồi cuối cùng chỉ `log_action(...)`; các action `block_ip`, `tighten_rate_limit`, `enable_honeypot` chưa thực sự thực hiện | SCP hiện có thể ghi nhận/escalate, nhưng chưa chứng minh đã chặn process, IP, exfiltration hay hành động nguy hiểm ngoài đời thật |
| **P0** | Human approve/reject và màn hình escalation chưa nối HTTP | `on_human_approval`, `on_human_rejection`, `get_dashboard_status` vẫn có TODO route; grep source không thấy `/v105/escalation/...` hoặc `/v105/capability/...` thật | Người vận hành không có đường chính thức để xem, duyệt, từ chối hoặc hủy một escalation. Nếu sau này playbook có hành động thật, đây là điểm phải hoàn thành trước |

### Giải thích về `.env`

Tôi **không sửa nội dung production `.env`**. Kết quả chỉ nói rằng quyền Windows hiện tại cho phép nhóm `CodexSandboxUsers` đọc file. Cần cân nhắc ACL riêng cho user `Minh\check`, `SYSTEM` và `Administrators`, nhưng phải kiểm tra Manus Desktop còn cần quyền gì trước khi thay đổi. Không nên tự ý đổi ACL rồi làm mất khả năng vận hành hoặc đồng bộ của Manus.

### Giải thích về Ollama

Đây là cấu hình của Ollama, không phải bằng chứng Ollama đang ăn cắp dữ liệu. Trong lúc kiểm tra không có process `ollama` chạy và không có port SCP nào mở. Tuy vậy, rule Public là cấu hình rộng hơn cần thiết. Cách đúng là giới hạn theo loopback/private profile và chỉ cho phép port cần thiết, không phải xóa Ollama.

## 2. Vấn đề chức năng chưa hoàn thành

| Mức | Phần | Trạng thái thật |
|---|---|---|
| **P1** | Cuộc gọi video giữa hai máy | Có signaling offer/answer/ICE, camera/mic permission và cleanup. Nhưng code tracked không có `iceServers`, `stun:` hoặc `turn:`. Vì vậy chưa có bằng chứng kết nối ổn định qua NAT/Internet; nhiều trường hợp chỉ chạy được cùng máy hoặc cùng mạng |
| **P1** | Token cuộc gọi | UI đang hiển thị trực tiếp chuỗi `call_id.token` để người dùng copy. Token có TTL ngắn nhưng ai nhìn thấy mã có thể vào phòng trong thời gian đó. Cần nút copy có cảnh báo, không ghi log, và có nút thu hồi phòng |
| **P1** | Evolution tự động | `run_evolution_cycle_once()` đã có nhưng comment trong `code_evolution_agent.py` ghi rõ chưa nối vào `deep_audit_loop`. `SCP_EVOLUTION_AUTO=0` và supervisor đang tắt. Vì vậy durable learning/evolution chưa phải chuỗi 24/7 đã chứng minh |
| **P1** | OTel | Source có `scp/observability/otel.py`, nhưng SDK không có trong Python venv, `.env` không bật `SCP_OTEL_ENABLED`, và PC chưa có OTLP collector. Đây mới là “có code tùy chọn”, chưa phải trace thật |
| **P1** | Installer có ký mã | Hai installer cuối đã tạo nhưng Authenticode là `NotSigned`. Hash mới nhất: x64 `87B5D50D0489C88F27F1B8AA04E84FEF5DE5239ED6262CC28595A754CF38AC34`; portable `451859F9F871F3151D936D958CC07983AD5DFBF13CD34E70F6ABC7F9E5AE743A` | PC khác có thể hiện SmartScreen warning. Đây là vấn đề tin cậy phát hành, không phải bằng chứng file bị nhiễm |
| **P1** | Camera/mic thật | Source có `getUserMedia`, MediaRecorder, capture ảnh và voice route. Package smoke chỉ chứng minh service/API, chưa chứng minh hai người dùng với webcam/mic thật nói chuyện hai chiều |
| **P1** | Cài trên PC thứ hai | Đã kiểm tra cấu trúc package và tạo installer, nhưng chưa cài hoàn chỉnh lên một PC thứ hai có môi trường sạch. Chưa có bằng chứng về quyền camera/mic, firewall, runtime VC++ và first-run migration trên máy khác |
| **P1** | 24/7 soak test | Chưa chạy soak 24 giờ hoặc 7 ngày sau các patch cuối. Chưa biết chắc memory leak, log tăng, SQLite lock và supervisor recovery sau mất điện/mất mạng |
| **P2** | Zalo/Telegram | Không có match trong file source tracked. Chưa có connector, webhook verification, chống replay, rate limit và policy gửi lệnh từ xa |
| **P2** | TTS/speech output | Không có đường `synthesize`/TTS trong source tracked. Mic input có một phần, nhưng SCP chưa nói lại như một cuộc gọi bằng giọng nói hoàn chỉnh |
| **P2** | Capability API | `capability_levels.py` có manager nhưng các route status/escalate/de-escalate vẫn là TODO. Người dùng chưa có luồng UI chính thức để quản lý capability |
| **P2** | Phát hiện ảnh adversarial | `image_voice_detector.py` ghi rõ phần pixel-level adversarial patch chưa làm; hiện chủ yếu OCR rồi tìm mẫu chữ. Ảnh nhiễu, QR độc hại, chữ nhỏ, steganography và prompt ẩn chưa được chứng minh bắt được |

## 3. Vấn đề về học, dự đoán và chất lượng AI

SCP có nhiều module học, dự đoán và tự sửa, nhưng số lượng module không đồng nghĩa với việc đã học đúng. Điểm benchmark cũ vẫn phải được giữ nguyên khi đánh giá:

| Chỉ số | Kết quả đã có | Ý nghĩa |
|---|---:|---|
| Factual-only | 0.3 | 3/10 câu đúng trong bộ đã chạy; chưa đủ tốt để coi là trợ lý đáng tin tuyệt đối |
| Self-correction | 0 | Trong bộ thử đó, SCP chưa chứng minh tự sửa thành công |
| Verifier consistency | 0.5 | Bộ kiểm tra và kết luận còn không nhất quán một phần |
| Security attack resistance | 0.6 | Có bypass; chưa được coi là bắt được mọi tấn công |

Một vấn đề nữa là các bộ test đang chứng minh **đường code đã chạy không lỗi**, chứ chưa chứng minh **semantic correctness** của mọi dự báo. Đặc biệt, 210 dự báo cũ chưa tự động trở thành “kiến thức đúng”; cần có nhãn kết quả về sau, thời điểm kiểm chứng, nguồn độc lập và trạng thái đúng/sai/không đủ dữ liệu.

## 4. Vấn đề về dữ liệu và bảo trì

| Mức | Quan sát | Tác động |
|---|---|---|
| **P1** | Thư mục `data` có khoảng 764 file, khoảng 181 MB | Có nguy cơ phình dần nếu 24/7 chạy lâu; cần retention, nén, archive và cảnh báo dung lượng |
| **P1** | `.private-secrets` có khoảng 7.2 GB, gồm nhiều backup/runtime/build cũ | Làm ổ đĩa đầy, tăng thời gian backup/scan và khiến người dùng khó biết file nào đang dùng. Cần phân loại `keep`, `rollback`, `temporary`, `delete-after-verification` |
| **P1** | Repo local có 99 mục untracked, trong đó khoảng 67 file/thư mục backup và nhiều script patch tạm | Dễ commit nhầm file cũ, chạy nhầm script, hoặc làm clean checkout khác PC thật. Không nên đưa tất cả lên GitHub |
| **P2** | `data`, `.private-secrets`, `desktop/runtime` được ignore nên clean clone không có runtime/data thật | Đây là lựa chọn đúng cho secret/data, nhưng phải phát hành kèm release asset có manifest/hash rõ ràng; tải source GitHub một mình chưa chạy được Desktop |
| **P2** | Installer build vẫn báo thiếu author và dùng default Electron icon | Không làm backend sai, nhưng làm sản phẩm thiếu chuyên nghiệp và khó tạo niềm tin khi phát hành |

## 5. Điểm đã được sửa trong lần audit này

Tôi phát hiện production guard trước đó chỉ kiểm tra bypass flags, egress mode và password; nó chưa chặn trường hợp `SCP_PRODUCTION_MODE=1` nhưng `SCP_HOST=0.0.0.0` và HTTPS tắt. Đã sửa `scp/security/production_guard.py` để **fail-closed** trong trường hợp đó, đồng thời sửa cảnh báo trong `api_server.py` để không coi `0.0.0.0` là loopback an toàn.

Bằng chứng bản vá: probe tạm cho kết quả `GUARD_BIND_POLICY=PASS`; binary mới chạy case non-loopback và ghi lỗi yêu cầu `SCP_FORCE_HTTPS`, không mở port; case loopback trả `health=200` và `CALL_CREATE=200`. Binary mới đã được đưa vào runtime và installer được rebuild.

## 6. Những việc đã kiểm tra lại sau bản vá

| Kiểm tra | Kết quả |
|---|---:|
| Full pytest sau hardening | 101 passed, 2 warnings |
| Reality harness sau hardening | 74/74 PASS, 0 FAIL, 0 TIMEOUT, 0 ERROR |
| Package smoke sau hardening | 4 port mở đúng, health 200, call create 200, call status 200 |
| Sau khi dừng package | 3000/3030/8000/11434 đều đóng |
| Supervisor | Disabled |
| Recovery Watchdog | Disabled |
| GitHub/PC source | Commit `d33f00d` |
| OTel package trên venv | Chưa cài |
| Installer Authenticode | NotSigned |

## 7. Thứ tự xử lý khuyến nghị

**Bước 1 — xử lý trước khi bật 24/7:** kiểm tra ACL `.env`, rà lại firewall rule Ollama Public, hoàn thiện route human approve/reject/status, và quyết định rõ defensive action nào thật sự được phép. Không nên bật auto-countermeasure thật khi playbook mới chỉ log.

**Bước 2 — hoàn thiện chức năng cốt lõi:** thêm STUN/TURN hoặc xác định rõ phạm vi chỉ gọi cùng mạng; kiểm tra hai PC có webcam/mic thật; cài installer trên PC sạch; thêm retention/rotation cho data và dọn `.private-secrets` có inventory.

**Bước 3 — chứng minh học và vận hành lâu dài:** nối evolution cycle vào scheduler có heartbeat riêng; gắn outcome thật cho dự báo cũ; chạy soak test 24 giờ rồi 7 ngày; thu trace OTel vào collector được kiểm soát.

**Bước 4 — phát hành rộng:** ký code Windows, đặt icon/author/version rõ, tạo release asset kèm manifest hash và hướng dẫn rollback. Sau đó mới cân nhắc Zalo/Telegram và TTS, vì messaging từ xa làm tăng rủi ro điều khiển máy ngoài ý muốn.

## Kết luận

SCP hiện đã là một **Release Candidate có nền tảng thật**, không còn chỉ là mô phỏng: source sạch đã chạy, package đã chạy, call API đã chạy, guard mới đã có bằng chứng, và test hiện tại pass. Nhưng phần “SCP tự động bắt mọi tấn công và phản công” vẫn chưa hoàn tất. Điểm thiếu lớn nhất không phải thêm thật nhiều module; điểm thiếu là nối các module thành hành động thật có kiểm soát, chứng minh bằng hai máy và thời gian chạy dài, đồng thời bảo vệ secret/Firewall/backup.

> **PASS hiện tại có nghĩa là:** không tìm thấy lỗi trong phạm vi và điều kiện đã kiểm tra. Nó không có nghĩa là SCP miễn nhiễm với mọi tấn công hoặc đã an toàn tuyệt đối.

## Tham chiếu

[1] [OWASP GenAI/LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[2] [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
[3] [OpenTelemetry FastAPI Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
