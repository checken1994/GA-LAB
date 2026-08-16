# Evidence chạy SCP 24/7 trên PC thật — 16/08/2026

## Kết luận hiện tại

SCP đã được bật trên PC Windows thật bằng hai scheduled task. Backend, loop scheduler, Ollama và dashboard production đều đã lên. Đây là bằng chứng vận hành thật đầu tiên, nhưng mới là **quan sát ban đầu**, chưa phải soak test 24 giờ.

> **Không được hiểu nhầm:** Supervisor đang `Running` và port đang mở chỉ chứng minh SCP đang chạy tại thời điểm kiểm tra. Nó chưa chứng minh SCP sẽ chạy ổn định cả ngày, không rò memory, không treo SQLite và tự phục hồi sau mất mạng.

## Bằng chứng runtime

| Thành phần | Trạng thái thật |
|---|---|
| `SCP-247-Supervisor` | `Running`, mã `0x00041301` — Windows báo task đang chạy |
| `SCP-247-Recovery-Watchdog` | `Ready`, mã `0` — task kiểm tra đã hoàn tất và đang chờ lần chạy theo lịch; không phải lỗi |
| Port dashboard | `3000` đang listen |
| Port loop scheduler | `3030` đang listen |
| Port Python backend | `8000` đang listen |
| Port Ollama | `11434` đang listen |
| Python backend `/health` | HTTP 200 |
| Dashboard `/api/scp/health` | HTTP 200 |
| Dashboard `/` | HTTP 200 |
| Runtime data | `subsystem_heartbeat.sqlite`, `v13.db-wal`, `request_runs.jsonl`, `fast_learning_runs.jsonl`, `learning_runs.jsonl` và các log khác tiếp tục được cập nhật |

File quan sát chính trên PC:

```text
C:\Users\check\Downloads\scp\scp-audit\runtime-247-observation-20260816-094128.json
```

File này chứa ba mẫu kiểm tra cách nhau 20 giây, gồm port, task, process, memory/CPU và kích thước các file log/WAL.

## Hai lỗi thật đã phát hiện khi bật 24/7

### 1. Scheduled Task trỏ nhầm PowerShell đã không còn tồn tại

Task ban đầu gọi PowerShell `7.6.4`, nhưng máy thật hiện có PowerShell `7.6.5`. Vì executable cũ không còn tồn tại, Supervisor trả mã `0x80070002` — nghĩa là Windows không tìm thấy file cần chạy. Khi đó cả 24/7 không khởi động được dù task vẫn tồn tại.

Tôi đã backup action cũ, đổi task sang executable hiện tại:

```text
C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.5.0_x64__8wekyb3d8bbwe\pwsh.exe
```

Backup nằm dưới thư mục `scp-audit` với tên bắt đầu bằng `task-fix-pwsh-`.

### 2. Dashboard chạy nhầm chế độ development

Supervisor cũ gọi `bun run dev`, tức là Next.js chạy Turbopack. Vì `dashboard/node_modules` đang là junction chuyển sang ổ D, Turbopack báo:

```text
Symlink [project]/node_modules is invalid, it points out of the filesystem root
```

Dashboard vì vậy bị panic và port 3000 không lên. Đây là lỗi chỉ lộ ra khi chạy 24/7 trên PC thật; CI build trước đó không có junction này.

Đã sửa service dashboard trong `scripts/ops/scp_247_supervisor.ps1` từ:

```text
bun run dev
```

sang:

```text
bun run start
```

`bun run start` dùng `.next/standalone/server.js`, tức bản production đã build sẵn, không quét lại `node_modules` bằng Turbopack. Bản sửa đã commit và push ở `15d729d`.

## Smoke test hội thoại thật

Tôi đã gửi câu hỏi vô hại qua chuỗi thật:

```text
dashboard 3000 → /api/scp/ask → Python backend 8000 → Ollama/luồng xử lý SCP → ledger
```

Kết quả có cả thành công và lỗi, đúng với nguyên tắc **PASS không có nghĩa là toàn hệ thống luôn đúng**.

| Run | Kết quả |
|---|---|
| `run-02d52bb4f7654ac2a2db3476a08cb5d6` | `SUCCESS`, các stage có `verdict=PASS`, kết thúc lúc khoảng 09:34:29 |
| `run-8c33f6011e284a38b115716ac84a4392` | `INTERNAL_FAILED`, có `request_received`, `request_started`, sau đó `request_finished` lỗi |

Điểm cần chú ý là request lỗi đã được ghi vào `request_runs.jsonl`, nhưng `error_store.jsonl` chưa có bản ghi lỗi chi tiết ánh xạ rõ với run đó. Đây là thiếu sót thật của **run ledger/error provenance**: biết request fail nhưng chưa biết chính xác provider, stage và exception nào chịu trách nhiệm.

Vì vậy, câu trả lời chính xác khi bạn kiểm tra là: **chuỗi khởi động và health đã chạy; luồng hỏi đáp chưa được tuyên bố ổn định hoàn toàn vì đã thấy ít nhất một INTERNAL_FAILED trong runtime thật.**

## Phần bạn có thể kiểm tra ngay

Bạn có thể mở dashboard/Desktop và thử các câu hỏi thông thường. Nếu một câu hỏi bị treo hoặc trả lời sai, thời điểm và câu hỏi đó cần đối chiếu với `request_runs.jsonl`, `error_store.jsonl`, `fast_learning_runs.jsonl` và log Supervisor.

Camera/mic vẫn cần bạn bấm quyền trên Windows và nói thật. Tôi không thể tự bấm Allow hoặc giả lập giọng nói của bạn rồi gọi đó là bằng chứng camera/mic thật.

## Những gì còn thiếu bằng chứng sau lần bật này

| Phần | Trạng thái |
|---|---|
| Chạy liên tục 24 giờ | Chưa đủ thời gian; mới là cửa sổ quan sát ban đầu |
| Tự phục hồi khi kill backend hoặc mất mạng | Chưa chạy fault injection trên phiên 24/7 này |
| Hỏi đáp ổn định nhiều lượt | Chưa đạt; đã có một run `INTERNAL_FAILED` |
| Trả lời đúng theo ngữ nghĩa | Chưa chứng minh cho mọi câu hỏi; cần đối chiếu câu hỏi–answer–verifier từng run |
| Camera/mic người dùng thật | Chưa có thao tác Allow và transcript thật |
| AutoFix sửa thật | Worker đang được giám sát nhưng chưa có evidence sửa một finding thật trong phiên này |
| Evolution/policy promotion | File ledger có hoạt động, nhưng chưa có promotion mới được verifier độc lập chứng minh trong phiên này |
| Memory/SQLite/log sau 24 giờ | Chưa đủ thời gian |
| Installer trên PC khác | Chưa kiểm tra |

## Rollback

Nếu cần tắt ngay phiên 24/7 hiện tại:

```powershell
Disable-ScheduledTask -TaskName 'SCP-247-Recovery-Watchdog'
Disable-ScheduledTask -TaskName 'SCP-247-Supervisor'
Stop-ScheduledTask -TaskName 'SCP-247-Recovery-Watchdog'
Stop-ScheduledTask -TaskName 'SCP-247-Supervisor'
```

Không dùng `git clean -fd` trên PC vì thư mục `scp-audit`, backup và dữ liệu runtime là evidence cần giữ lại.

**Tác giả:** Manus AI  
**Ngày:** 16/08/2026
