# SCP Release Candidate — Reality Final

**Ngày evidence:** 15/08/2026 theo timezone PC; **phạm vi:** PC Windows thật `C:\Users\check\Downloads\scp`, sandbox regression và GitHub `checken1994/GA-LAB`.

## Kết luận điều hành

SCP hiện đạt trạng thái **release candidate có thể đóng gói và chạy trên đúng PC đã kiểm thử**. Không nên gọi đây là “đã chứng minh production trên mọi PC” hoặc “tự động bắt được mọi cuộc tấn công”. Những tuyên bố đó vượt quá evidence.

Trạng thái vận hành cuối sau khi restart có kiểm soát là: Task Supervisor `Running`, bốn port `3000/3030/8000/11434` đang listen và worker status trả `llm_allowed=false`, `applied=1`, `rejected=1`. Snapshot runtime cuối ghi `fast_learning=IDLE/fresh=True`, `evolution=DISABLED/fresh=True`, `deep_audit=IDLE/fresh=True`, `attack_monitor=IDLE/fresh=True`. Evolution được tắt có chủ ý; `DISABLED` không phải lỗi chết loop.

Một reality test quan trọng đã tìm ra lỗi thật: cycle FastLearning bị hủy bởi giới hạn thời gian nhưng ledger ghi nhầm `TELEMETRY_DEGRADED` thay vì `TIMEOUT`. Nguyên nhân là cờ nội bộ chỉ được bật sau khi task đã bị hủy. Bản vá giữ cờ trong suốt lúc `CancelledError` lan qua decorator, sau đó live test trên PC đã ghi đúng `cycle_completed|STATUS=TIMEOUT|ERROR=CancelledError`, cycle được kết thúc và heartbeat quay về `IDLE/fresh=True`.

Reality test cũng phát hiện supervisor mỗi lần restart tự ghi đè `child-safe.env`, làm mất các dòng Evolution/telemetry/timeout mà ta thêm thủ công. Đã sửa supervisor để tự tạo lại toàn bộ boundary an toàn mỗi lần khởi động; lần restart sau bản vá xác nhận đủ năm tên cờ bắt buộc và không chạm `C:\Users\check\Downloads\.env`.

## Các thay đổi đã hoàn tất

| Khu vực | Thay đổi | Evidence |
|---|---|---|
| AutoFix route | Observe-only bounded scan; apply route hỗ trợ deterministic-only | `af34422`, `97967cd` |
| AutoFix production loop | `SCP_AUTOFIX_MODE=apply`, `SCP_MAX_AUDIT_BUGS=5`, `SCP_AUTOFIX_DETERMINISTIC_ONLY=1`; tối đa 50 file scan trong bounded path | Child safe env trên PC |
| Auth | Private token file được truyền qua `SCP_AUTH_TOKEN_SECRET_FILE` và `SCP_SCHEDULER_ADMIN_TOKEN_FILE`; không sửa production `.env` | Supervisor commits `7d1579b` đến `cfc03f4` |
| Scheduler | Đúng contract `SCP_SCHEDULER_ADMIN_TOKEN_FILE`; loop control được xác thực, bind loopback | `cfc03f4`, `a0b2ea5` |
| Orphan process | Windows Job Object với `KILL_ON_JOB_CLOSE`; external terminate đã dừng child | Supervisor evidence/ledger |
| Recovery | Recovery watchdog mỗi phút, user-session scope; kill switch được tôn trọng | `a364ae7`, `d6b0b96` |
| Packaging | Runtime manifest, build script hash binaries; Electron filter loại `data`, `.py`, `.env`, DB/JSONL khỏi bundle | `0039e41`, `e46515d` |
| Tests | Fixture Windows path được sửa thành portable `tmp_path`; telemetry timeout và supervisor child-safe contract được thêm | `92 passed` sandbox; PC runtime timeout + 4 port check pass |

## AutoFix: đã tự động đến mức nào?

AutoFix hiện có **deterministic worker ngoài HTTP loop**. Loop Scheduler chỉ bounded-scan và enqueue; worker được supervisor quản lý, dùng SQLite queue/lease, source-hash baseline, AST recipe, policy gate, atomic apply, AST/postcondition verify, rollback token và forensic audit. Worker có `SCP_AUTOFIX_WORKER_ALLOW_LLM=0` hard-coded trong config và không có provider path. Finding không match recipe, stale hash, policy/audit failure hoặc risk vượt `low` trở thành `candidate`/`rejected`, không tự sửa.

Các recipe deterministic hiện có là `bare_except_pass_ast_v1` (low), `open_encoding_ast_v1` (low) và `sql_parameterize_ast_v1` (medium nhưng mặc định chỉ candidate). Worker chạy `--watch`, polling 30 giây, tối đa 1 job/cycle, lease 180 giây và tối đa 2 retry. Đây là cách xử lý finding phức tạp hơn mà không đưa LLM vào loop: mở rộng recipe AST/data-flow hẹp, không mở rộng quyền apply.

Reality test queue/apply trên PC thật trả:

| Trường | Giá trị |
|---|---:|
| HTTP enqueue | `200` |
| `mode` | `queued` |
| `worker` | `deterministic` |
| `jobs_enqueued` | `1` |
| Sau polling | `applied=1`, `rejected=1` trong queue ledger |
| `llm_allowed` | `false` |
| Worker binary one-shot | exit `0`, queue rỗng, `failed=0` |
| PC targeted tests | `16 passed` |

Đây là kết quả **đúng nghĩa**: HTTP 200 chỉ chứng minh enqueue; aggregate queue sau polling chứng minh worker đã claim/apply một job và reject một job không có recipe phù hợp. `llm_allowed=false` được trả trực tiếp từ worker status. Job state được phân biệt bằng ledger, không còn nhầm `HTTP 200` với `fixed=1`. Các lần thử trước khi có bounded route đã timeout vì scanner/LLM audit đồng bộ quá nặng; hiện tại deterministic worker không phụ thuộc bridge/provider.

## Job Object và watchdog 24/7

Supervisor tạo Job Object và đặt `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (`0x2000`), sau đó assign các child Bun/Python vào job. External termination test xác nhận child listeners bị dừng thay vì trở thành orphan. Đây giải quyết lỗi hash drift do Python orphan tiếp tục ghi `v13.db` sau khi supervisor biến mất.

Watchdog chạy mỗi phút bằng user `check`, `Interactive`, `RunLevel Limited`. Việc đăng ký SYSTEM task đã bị Windows từ chối với `Access is denied`; installer đã được sửa để ghi đúng **user-session scope**, không tuyên bố giả rằng nó đã đạt pre-logon service scope. Khi terminate supervisor, watchdog đã ghi `WATCHDOG_RECOVERY_START`; lần recovery đầu có độ trễ do trigger theo phút và task launch, sau đó ledger ghi START/HEALTHY cho bốn service và checkpoint cuối trả bốn port listen.

Do đó, watchdog hiện **đủ để tự hồi phục trong phiên user đang đăng nhập**, nhưng chưa đủ để chứng minh chạy trước logon, sau logoff hoặc sau cold boot. Muốn đạt nền 24/7 thật sự không phụ thuộc phiên đăng nhập, cần Windows Service hoặc Scheduled Task chạy bằng service account/SYSTEM được cài bằng installer elevated, kèm secret/ACL model riêng.

## Packaging evidence

Electron portable build từ bốn runtime binaries, gồm deterministic worker, đã thành công trên PC thật theo source HEAD mới.

| Artifact | Kết quả |
|---|---:|
| Portable artifact | `SCP-DNA-Control-Center-1.6.0-portable.exe` |
| Size | `625,549,371` bytes |
| SHA-256 | `212A7C4D89A46CC9443704983D4ED7EAE02642EBBD524F5895AA642AB2D65B54` |
| Embedded `scp-backend.exe` | Có |
| Embedded `scp-llm-bridge.exe` | Có |
| Embedded `scp-loop-scheduler.exe` | Có |
| Embedded `scp-autofix-worker.exe` | Có; SHA-256 `EB41302169785AB08B2547C4E28D3BA4DC0C8CBC7CF3A607F8715F264B11FBED` |
| Embedded live `data/` | Không |
| Embedded Python source | Không |
| Embedded `.env` | Không |

Runtime binaries được rebuild vào staging trước khi đóng gói; binary đang chạy trên PC được backup và restore atomic sau build. Binaries không được commit trực tiếp vào GitHub source vì kích thước lớn và chứa artifact nền tảng; release bundle phải mang manifest/hash riêng.

## `v13.db` và data boundary

`v13.db` vẫn là **runtime writable database**, không phải policy file bất biến. Các bảng telemetry như `question_events`, `question_log`, `healing_history` và `pending_reverification` có thể tăng khi backend hoạt động. `SCP_ENABLE_CLOSED_LOOP=0` chỉ khóa closed-loop policy promotion; nó không có nghĩa mọi telemetry writer đều bị tắt.

Vì vậy production operation phải coi hash drift của `v13.db` là expected runtime mutation cần audit, không dùng hash file đơn lẻ để kết luận policy mutation. Snapshot phải dùng SQLite backup API nhất quán, manifest atomic, `integrity_check`, table counts và hash snapshot. Không restore live DB khi writer còn chạy.

## Regression và release gates

Sandbox regression cuối sau các source patches: **92 pytest passed, 0 failed**. Trong đó có test ledger TIMEOUT khi task bị cancel và test supervisor không làm mất child-safe boundary. PC thật đã chạy live restart, kiểm tra bốn port listen, supervisor `Running`, worker `llm_allowed=false`, Evolution `DISABLED/fresh=True`, cùng live FastLearning timeout ghi đúng `TIMEOUT` rồi quay về `IDLE/fresh=True`. Queue evidence vẫn là `applied=1`, `rejected=1`. Desktop JavaScript syntax check và portable Electron build vẫn giữ evidence trước đó. Hai PID Python có cùng command line là cặp venv launcher/base interpreter của một logical worker, không phải hai job worker độc lập.

## Blocker còn lại trước khi gọi là Production phổ quát

| Mức | Giới hạn | Ý nghĩa |
|---|---|---|
| P0 release evidence | Chưa test installer trên PC Windows thứ hai | Chưa chứng minh clean-machine portability |
| P0 lifecycle | Watchdog hiện user-session, chưa pre-logon | Logoff/cold boot vẫn là khoảng trống |
| P1 trust | Portable artifact chưa có Authenticode publisher signature | Windows trust UX và provenance chưa hoàn chỉnh |
| P1 operations | Chưa chứng minh disk-full/log rotation/ledger write failure | Có thể mất audit evidence nếu storage cạn |
| P1 runtime | Live `v13.db` vẫn writable telemetry | Cần tách telemetry khỏi policy state nếu muốn immutable policy boundary |
| P1 AutoFix | Worker deterministic đã có queue/job ID/lease/rollback nhưng semantic coverage còn hẹp | Mở rộng từng recipe AST/data-flow với fixture, postcondition và fault injection; không nâng `auto_apply_risk` nếu chưa có evidence |
| P2 resilience | Sleep/hibernate/provider outage dài chưa test đầy đủ | Chưa có evidence cho mọi interruption mode |
| P2 security | Không có bằng chứng SCP bắt được “tất cả” AI/con người attacks | Chỉ có coverage theo detectors/fixtures đã tồn tại |

## Quy trình rollback

Nếu release candidate có lỗi, trước hết tạo kill switch tại `.private-secrets\release-audit\scp-247\KILL`. Supervisor sẽ dừng child theo Job Object. Giữ lại task XML, supervisor backup, runtime binary backup và SQLite snapshot. Sau đó restore source/binaries bằng artifact backup, xóa `KILL` chỉ sau khi đã kiểm tra hash và start lại task. Không restore `v13.db` khi còn listener; phải dừng toàn bộ writers, restore snapshot qua SQLite-safe path, chạy integrity check và ghi manifest mới.

## GitHub state

Source và tests đã đồng bộ lên `GA-LAB`:

- `8b3d6b9` — supervised deterministic AutoFix worker, AST recipes, queue status và packaged worker contract.
- `97967cd` — bounded deterministic AutoFix scan workload.
- `af34422` — production AutoFix deterministic-only boundary.
- `e46515d` — exclude live runtime data from desktop packaging.
- `0039e41` — desktop runtime release contract and portable tests.
- `d6b0b96` — truthful user-session recovery watchdog scope.
- `210fe8c` — explicitly treat deliberate Evolution DISABLED state as fresh.
- `174b8bb` — bounded FastLearning cycle and terminal timeout ledger.
- `f4e1d4d` — classify bounded cancellation as TIMEOUT, not degraded telemetry.
- `e1736b0` — preserve child-safe Evolution/telemetry/timeout flags on supervisor restart.

GitHub source HEAD được xác nhận là `e1736b0c09ee61b3000501a01da7eec4230e41d5` với source/tests working tree sạch trong sandbox clone. Binary worker và portable artifact không commit vào source repo; chỉ lưu hash/evidence.

## Kết luận cuối

SCP có thể được gọi là **release candidate đã reality-test trên một PC Windows cụ thể**, hiện đã có deterministic worker ngoài loop, heartbeat/ledger riêng cho các subsystem, bounded FastLearning timeout và portable artifact chứa worker. Có thể chạy nền trong phiên user với supervisor, Job Object, kill switch, watchdog user-session, closed-loop OFF, bounded queue và AutoFix deterministic-only.

SCP **chưa được gọi là production phổ quát hoặc hoàn thiện tuyệt đối** cho đến khi có clean-machine test trên PC thứ hai, pre-logon service boundary, publisher signature, disk/log failure tests, sleep/hibernate/provider-outage evidence và mở rộng semantic coverage của recipes. LLM không nằm trong production loop hiện tại; nếu sau này cần LLM, nó phải là approval/research worker độc lập với timeout/cancel và không được cấp quyền apply trực tiếp. Đây là kết luận phù hợp với DNA #22: **PASS không đồng nghĩa TRUE ở ngoài phạm vi evidence**.
