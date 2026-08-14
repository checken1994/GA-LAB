# SCP 24/7 — Job Object, Runtime Growth và Timeline Limits

**Ngày:** 2026-08-14  
**PC thật:** `C:\Users\check\Downloads\scp`  
**Supervisor source SHA-256 trên PC:** `89EBF54AF9CB411B94BEC673453814E87BC62C4AFBC1ECA71EE107D6C27C6441`

## 1. Kết luận ngắn

Cấu hình Windows Job Object hiện tại đã giải quyết đúng lỗi **orphan Bun/Python/Node processes**. Supervisor tạo một Job Object, bật `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` bằng cờ `0x2000`, rồi assign từng process được tạo bởi `Start-Process` vào job. Reality test đã terminate trực tiếp supervisor PowerShell: cả bốn port 3000, 3030, 8000 và 11434 đóng; sau đó khởi động lại task, cả bốn port trở lại và process lineage của từng listener có ancestor là supervisor.

Không nên tắt các giới hạn thời gian an toàn. **Total task execution limit hiện đã là `PT0S`, tức không giới hạn thời gian chạy.** Các timeout còn lại là những bounded safety limits khác: health request timeout, restart window 900 giây, restart budget 5 lần và fault-injection observation window. Chúng không phải lỗi cần tắt; tắt chúng sẽ làm SCP dễ treo, restart-loop hoặc che giấu failure.

## 2. Cấu hình Job Object hiện tại

Supervisor nhúng một lớp C# P/Invoke qua `Add-Type`. Các API Windows được dùng là:

| Thành phần | Cấu hình thực tế | Ý nghĩa |
|---|---|---|
| `CreateJobObject` | Tạo job không đặt tên | Supervisor giữ handle sống trong process PowerShell |
| `SetInformationJobObject` | `JobObjectExtendedLimitInformation` | Ghi extended limits cho job |
| Limit flag | `0x2000 = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` | Đóng handle cuối cùng sẽ terminate process trong job |
| `AssignProcessToJobObject` | Gọi ngay sau mỗi `Start-Process` | Đưa Bun/Python/Node wrapper vào containment |
| `CloseHandle` | Gọi trong `finally` | Khi supervisor kết thúc, Job Object đóng và child bị dừng |
| Breakaway flags | Không bật `BREAKAWAY_OK` hoặc `SILENT_BREAKAWAY_OK` | Descendants không được phép tự tách khỏi job theo cấu hình hiện tại |
| CPU/memory limit | Không đặt | Job Object hiện chỉ là lifecycle containment, không phải resource quota |
| Completion port | Chưa cấu hình | Chưa có notification channel cho quota/process events |

Theo tài liệu Microsoft, Job Object dùng để quản lý một nhóm process như một đơn vị; process con được tạo bình thường sẽ tiếp tục thuộc job, và `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` sẽ terminate mọi process liên quan khi handle cuối cùng đóng [1]. Đây chính là cơ chế đang dùng cho SCP.

### Điểm cần phân biệt

Job Object **không làm cho SQLite read-only** và không ngăn một Python process bên trong job ghi `data\v13.db`. Nó chỉ bảo đảm rằng khi supervisor chết, Python/Bun/Node cũng chết theo. Vì vậy containment process và database write isolation là hai lớp khác nhau:

> **Job Object giải quyết “ai còn sống”; snapshot/observation-only contract giải quyết “ai được phép ghi dữ liệu”.**

## 3. Tích hợp với Bun/Python processes

Supervisor gọi `Start-Process` cho bốn runtime:

| Service | Runtime | Process boundary |
|---|---|---|
| LLM Bridge | `bun run dev` | Bun wrapper và descendants |
| Loop Scheduler | `bun run dev` | Bun wrapper và descendants |
| SCP Python | `python.exe -m scp 8000` | Python server và process descendants nếu có |
| Dashboard | `bun run dev` | Bun/Node wrapper và descendants |

Bun dev servers thường tạo thêm process Node/Bun bên dưới. Python có thể tạo threads và có thể tạo subprocess tùy đường code. Job Object quản lý process descendants; threads bên trong Python vẫn nằm trong cùng Python process và sẽ dừng khi Python process bị terminate.

Reality evidence sau khi Job Object được cài:

| Test | Kết quả |
|---|---|
| Terminate trực tiếp supervisor PID | Đã thực hiện |
| Port 3000 sau terminate | `False` |
| Port 3030 sau terminate | `False` |
| Port 8000 sau terminate | `False` |
| Port 11434 sau terminate | `False` |
| Khởi động lại task | 4 port trở lại `True` |
| Process lineage sau recovery | 4 listener có ancestor supervisor |
| Task cuối | `Running` |

Đây là bằng chứng lifecycle thực tế. Tuy nhiên, chưa gọi trực tiếp `IsProcessInJob` hoặc `QueryInformationJobObject` để đọc membership/accounting. Bằng chứng hiện tại là hành vi external-kill và ancestor lineage; bước hardening tiếp theo nên thêm một probe native `IsProcessInJob` vào health audit để chứng minh membership trực tiếp thay vì suy luận từ process tree.

## 4. Biểu đồ tăng trưởng runtime tables T0–T90

![Biểu đồ tăng trưởng question_events và healing_history](runtime_growth_t0_t90.png)

Dữ liệu trên là các row counts đọc bằng SQLite read-only audit trên PC thật, không phải dữ liệu mô phỏng.

| Mốc | `question_events` | Delta từ T0 | `healing_history` | Delta từ T0 |
|---|---:|---:|---:|---:|
| T0 | 17.097 | 0 | 28.662 | 0 |
| T45 | 17.156 | +59 | 28.761 | +99 |
| T90 | 17.191 | +94 | 28.820 | +158 |

Trong 90 giây, `question_events` tăng **94 row**, tương đương khoảng **0,55%** so với T0 và trung bình **1,04 row/giây**. `healing_history` tăng **158 row**, tương đương khoảng **0,55%** và trung bình **1,76 row/giây**. Tại cùng các lần đọc, `PRAGMA integrity_check` trả `ok`.

Biểu đồ chứng minh **runtime writer activity**, không chứng minh các row là external truth, policy lesson hoặc learned knowledge. Sự tăng trưởng của `healing_history` cũng không có nghĩa SCP đang tự động promote policy; `SCP_ENABLE_CLOSED_LOOP=0`, `experiences` và policy artifacts vẫn phải được kiểm tra độc lập.

## 5. Có cần tắt giới hạn timeline không?

Câu trả lời là **không tắt toàn bộ timeline limits**. Cần tách bốn loại giới hạn:

| Loại giới hạn | Giá trị/trạng thái | Quyết định |
|---|---|---|
| Task Scheduler total execution limit | `PT0S` | Đã unlimited; không cần tắt gì thêm |
| Health HTTP timeout | Khoảng 4–5 giây ở supervisor | Giữ; tránh healthcheck treo vô hạn |
| Restart budget/window | 5 lần trong 900 giây | Giữ; ngăn restart-loop và bảo vệ provider/DB |
| Fault-injection observation window | 45 giây trong test harness | Giữ; đây là safety boundary của test, không phải production uptime limit |
| Task wake-up | `Wake=False` | Không tự ý bật; đây là quyết định power-management, không phải watchdog timeout |
| `AtLogOn` trigger | Chạy khi user logon | Không tắt; nhưng phải ghi rõ chưa phải boot-before-logon service |

Nếu “timeline” người dùng nói là **thời gian chạy 24/7**, SCP đã không bị giới hạn: `ExecutionTimeLimit=PT0S`. Nếu “timeline” là **restart window/observation timeout**, không nên tắt. Các hệ thống production không bỏ timeout; chúng dùng timeout để chuyển failure thành trạng thái quan sát được, sau đó retry/backoff/circuit-breaker.

Nếu mục tiêu là SCP chạy cả khi chưa đăng nhập hoặc sau reboot trước logon, vấn đề không phải tắt timeout. Cần chuyển từ user-level `AtLogOn` sang Windows Service hoặc Scheduled Task `AtStartup` với identity/quyền được thiết kế riêng. Đây là thay đổi quyền và môi trường, nên không nên tự động áp dụng trong phiên này.

## 6. Các hệ thống khác xử lý vấn đề tương tự như thế nào?

### Windows Job Object

Windows dùng Job Object để gom process và áp giới hạn/lifecycle ở cấp nhóm. Đây là lớp gần nhất với bản vá SCP hiện tại. Điểm mạnh là kill descendants khi handle đóng; điểm yếu là Job Object không tự cung cấp health semantics, restart backoff, database transaction policy hay readiness probe. Supervisor vẫn phải xây các lớp đó [1].

### systemd trên Linux

systemd mặc định dùng `KillMode=control-group`: khi service stop, tất cả process còn lại trong control group bị xử lý, thay vì chỉ kill main PID. Tài liệu systemd cảnh báo `KillMode=process` hoặc `none` cho phép process thoát khỏi lifecycle manager; cơ chế stop thường gửi SIGTERM trước rồi SIGKILL sau `TimeoutStopSec` nếu process không thoát [2]. Đây là mô hình tương đương với **Job Object + graceful timeout + forced cleanup**. systemd không khuyến nghị tắt timeout; timeout là phần của correctness.

### Kubernetes

Kubernetes tách lifecycle khỏi process cha. Kubelet chạy probes, restart container theo `restartPolicy`, áp exponential backoff khi container crash, và controller có thể thay Pod thay vì cố cứu một instance hỏng. Kubernetes cũng coi Pod là tương đối ephemeral; dữ liệu bền vững phải nằm ở volume/external store, không nên phụ thuộc vào filesystem writable của container [3]. Mô hình này tương ứng với SCP theo cách sau:

| Kubernetes | SCP tương đương |
|---|---|
| Pod/container lifecycle | Job Object + supervisor child lifecycle |
| Liveness/readiness probes | HTTP health checks |
| `restartPolicy` + backoff | bounded restart + circuit breaker |
| Controller replaces Pod | Supervisor restart/recovery |
| PersistentVolume/external state | SQLite snapshot/rollback contract |
| CrashLoopBackOff | `CIRCUIT_OPEN` |

SCP hiện đã có bốn hàng đầu nhưng lớp persistent-state isolation còn yếu: runtime `v13.db` vẫn writable trong live process. Vì vậy SCP chưa nên tự nhận là tương đương Kubernetes về data lifecycle.

## 7. Khuyến nghị theo thứ tự ưu tiên

**P0 — Giữ Job Object và thêm membership probe.** Bổ sung `IsProcessInJob`/`QueryInformationJobObject` vào audit, ghi `job_membership=true/false` cho từng child. Nếu membership probe fail, supervisor phải fail-closed và không tuyên bố healthy.

**P1 — Tách availability telemetry khỏi learning/policy state.** `question_events`, `healing_history` và các runtime counters cần có provenance/run ID và retention policy. `SCP_ENABLE_CLOSED_LOOP=0` chỉ đủ để khóa policy promotion; chưa đủ để bảo đảm DB không đổi.

**P1 — Fault injection luôn snapshot trước.** Snapshot v2 đã tạo manifest atomic, integrity và row counts. Không chạy test nếu manifest không `COMPLETE`. Rollback chỉ thực hiện sau khi toàn bộ writer đã bị Job Object dừng.

**P2 — Bổ sung boot-before-logon test.** Không tắt timeout; quyết định trước là user-level interactive canary hay Windows Service. Hai mô hình có quyền, secret loading và recovery semantics khác nhau.

## 8. Kết luận DNA

> **Không tắt timeline limits để làm cho hệ thống “trông như 24/7”. Unlimited uptime và bounded failure handling là hai yêu cầu khác nhau.**

SCP hiện đã có process containment đúng hướng: Job Object giữ Bun/Python/Node trong cùng lifecycle và external-kill test đã chứng minh không còn orphan trong phạm vi đã kiểm tra. Runtime table growth là bằng chứng writer activity, không phải bằng chứng policy learning. Missing piece còn lại là membership probe trực tiếp và data-write isolation/provenance.

## References

[1] [Microsoft Learn — Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)  
[2] [freedesktop.org — systemd.kill / KillMode](https://www.freedesktop.org/software/systemd/man/systemd.kill.html)  
[3] [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
