# Review ledger SCP-247-Recovery-Watchdog — 16/08/2026

## Kết luận

Ledger đã ghi lại hoạt động của **Supervisor và các service**, không chỉ riêng watchdog. Vì vậy phải đọc cùng với Task Scheduler để không nhầm event health/restart của Supervisor là một lần watchdog tự phục hồi.

Tại thời điểm kiểm tra:

| Thành phần | Trạng thái |
|---|---|
| `SCP-247-Recovery-Watchdog` | `Disabled` |
| Lần chạy cuối của watchdog | Khoảng `10:14:15` |
| Event Task Scheduler disable | `10:14:59`, Event ID `142` |
| `SCP-247-Supervisor` | `Running` |
| Port `3000/3030/8000/11434` | Đều đang mở |

Việc đọc ledger không làm thay đổi task. Watchdog đã bị disable trong runtime trước thời điểm review; không phải do lệnh đọc log.

## Chất lượng file ledger

File được kiểm tra:

```text
C:\Users\check\Downloads\scp\.private-secrets\release-audit\scp-247\supervisor-ledger.jsonl
```

Trong toàn bộ file có **1.946 dòng**, gồm **973 dòng JSON hợp lệ** và **973 dòng trống**. Dòng trống không phải hoạt động mới, nhưng làm file ledger phình gấp đôi và khiến việc đọc bằng công cụ đơn giản dễ hiểu sai. Đây là điểm nên sửa sau: writer nên ghi đúng một JSON object trên một dòng, không tạo dòng rỗng.

## Các event gần đây

Trong 100 record hợp lệ gần nhất:

| Event | Số lần | Ý nghĩa |
|---|---:|---|
| `HEALTHY` | 78 | Process được nhìn thấy; một số lần có cả HTTP probe thành công |
| `CIRCUIT_OPEN` | 19 | Không cho restart thêm vì đã vượt restart budget |
| `RESTART` | 1 | Có một lần restart được ghi nhận |
| `START` | 1 | Supervisor ghi nhận bắt đầu service |
| `STOP` | 1 | Có một lần stop được ghi nhận |

Các service xuất hiện trong 100 record:

| Service | Số record |
|---|---:|
| `scp-python` | 22 |
| `autofix-worker` | 20 |
| `dashboard` | 20 |
| `llm-bridge` | 19 |
| `loop-scheduler` | 19 |

Các lý do chính:

| Reason | Số lần | Ý nghĩa |
|---|---:|---|
| `process_and_http_ok` | 58 | Process và HTTP đều được kiểm tra thành công |
| `process_ok_no_http_probe` | 20 | Process có mặt nhưng service không có HTTP probe tương ứng hoặc lần đó không probe |
| `restart_budget_exhausted` | 19 | Circuit breaker đã mở, không restart vô hạn |
| `health_failure` | 2 | Có hai lần health check không đạt |
| `supervisor_start` | 1 | Ghi nhận bắt đầu Supervisor |

## Bất thường quan trọng

Record `CIRCUIT_OPEN` gần nhất liên quan đến `llm-bridge`, với lý do `restart_budget_exhausted`. Điều này có nghĩa Supervisor đã quyết định **không tiếp tục restart vô hạn** cho service đó. Đây là hành vi an toàn hơn retry mù, nhưng cũng có nghĩa `llm-bridge` có thể bị bỏ lại không phục vụ nếu không có người kiểm tra nguyên nhân.

Ledger còn ghi một số `HEALTHY` với `process_ok_no_http_probe`. Không được coi các record này là HTTP health PASS; chúng chỉ chứng minh process còn tồn tại. Đây là khác biệt quan trọng giữa “process còn sống” và “service hoạt động đúng”.

## Diễn giải đúng về watchdog

Watchdog script chỉ kiểm tra trạng thái task Supervisor. Nếu Supervisor đang Running, nó ghi trạng thái khỏe và thoát. Nếu Supervisor bị dừng, watchdog có thể gọi `Start-ScheduledTask`, trừ khi có kill switch hoặc Supervisor đang Disabled. Nó không tự sửa code, không tự promote policy và không tự chứng minh LLM trả lời đúng.

Do watchdog hiện Disabled từ Event ID 142 lúc `10:14:59`, các record sau mốc đó trong ledger là hoạt động của Supervisor/service, không phải các lần watchdog mới. Muốn biết watchdog chạy bao nhiêu lần phải lọc thêm Task Scheduler event log, không chỉ đọc ledger dùng chung.

## Việc nên làm tiếp theo

Thứ nhất, giữ watchdog Disabled trong lúc debug nếu không muốn PowerShell mới mở mỗi phút. Supervisor và các service hiện tại vẫn đang chạy, nhưng nếu Supervisor chết thì sẽ không tự phục hồi.

Thứ hai, khi cần 24/7, bật lại bằng script có backup:

```powershell
cd C:\Users\check\Downloads\scp
.\scripts\control_scp_247_watchdog.ps1 -Action Enable -StartAfterEnable
```

Thứ ba, sửa writer ledger để bỏ dòng trống và thêm trường phân biệt `actor=watchdog` với `actor=supervisor`. Nếu không, các lần chạy watchdog và các health event của Supervisor tiếp tục bị trộn trong cùng file.

**Không có secret raw trong báo cáo này.**

**Ngày:** 16/08/2026  
**Tác giả:** Manus AI
