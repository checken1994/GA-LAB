# SCP Release Candidate — Reality Final

**Ngày evidence:** 15/08/2026 theo timezone PC; **phạm vi:** PC Windows thật `C:\Users\check\Downloads\scp`, sandbox regression và GitHub `checken1994/GA-LAB`.

## Kết luận điều hành

SCP hiện đạt trạng thái **release candidate có thể đóng gói và chạy trên đúng PC đã kiểm thử**. Không nên gọi đây là “đã chứng minh production trên mọi PC” hoặc “tự động bắt được mọi cuộc tấn công”. Những tuyên bố đó vượt quá evidence.

Trạng thái vận hành cuối sau khi resume loop là: Task Supervisor `Running`, bốn port `3000/3030/8000/11434` đang listen và các health endpoint kiểm tra cuối đều HTTP `200`. Loop Scheduler đã được resume, `paused=false`; giá trị `last_run` còn hiển thị lỗi cũ và `scp_online=false` từ lần request timeout/startup race trước đó, nên không được đọc nhầm thành health hiện tại. Probe trực tiếp sau đó cho thấy backend, scheduler healthz và LLM Bridge đều `200`.

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
| Tests | Fixture Windows path được sửa thành portable `tmp_path`; toàn bộ sandbox pytest pass | `81 passed` |

## AutoFix: đã tự động đến mức nào?

AutoFix **đã được nối end-to-end**, nhưng không phải mọi bug đều tự sửa. Luồng hiện tại có ba lớp. Findings có search/replace patch có sẵn, BareExceptPass và các deterministic patterns được phép đi qua engine với backup/verify/rollback contract. Findings phức tạp không có deterministic patch bị ghi nhận là `skipped` khi production loop đặt `SCP_AUTOFIX_DETERMINISTIC_ONLY=1`; chúng không gọi LLM và không tự sửa.

Reality test apply trên PC thật với `max_bugs=1` trả:

| Trường | Giá trị |
|---|---:|
| HTTP | `200` |
| `mode` | `apply` |
| `deterministic_only` | `true` |
| `audit_complete` | `true` |
| `processed` | `1` |
| `fixed` | `0` |
| `permission_requested` | `0` |
| `skipped` | `1` |
| `source` | `bounded_ast_scan_deterministic_only` |
| Thời lượng | `16 giây` |

Đây là kết quả **an toàn và đúng nghĩa**: hệ thống đã phát hiện một finding nhưng không có patch deterministic được chứng minh là an toàn nên không tự sửa. `fixed=0` không phải lỗi; đó là hành vi fail-closed. Các lần thử trước khi có bounded route đã timeout vì scanner/LLM audit đồng bộ quá nặng; request bị dừng và loop được pause trước khi restart sạch. Không nên lấy các lần timeout đó làm bằng chứng AutoFix hiện tại đã pass.

## Job Object và watchdog 24/7

Supervisor tạo Job Object và đặt `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (`0x2000`), sau đó assign các child Bun/Python vào job. External termination test xác nhận child listeners bị dừng thay vì trở thành orphan. Đây giải quyết lỗi hash drift do Python orphan tiếp tục ghi `v13.db` sau khi supervisor biến mất.

Watchdog chạy mỗi phút bằng user `check`, `Interactive`, `RunLevel Limited`. Việc đăng ký SYSTEM task đã bị Windows từ chối với `Access is denied`; installer đã được sửa để ghi đúng **user-session scope**, không tuyên bố giả rằng nó đã đạt pre-logon service scope. Khi terminate supervisor, watchdog đã ghi `WATCHDOG_RECOVERY_START`; lần recovery đầu có độ trễ do trigger theo phút và task launch, sau đó ledger ghi START/HEALTHY cho bốn service và checkpoint cuối trả bốn port listen.

Do đó, watchdog hiện **đủ để tự hồi phục trong phiên user đang đăng nhập**, nhưng chưa đủ để chứng minh chạy trước logon, sau logoff hoặc sau cold boot. Muốn đạt nền 24/7 thật sự không phụ thuộc phiên đăng nhập, cần Windows Service hoặc Scheduled Task chạy bằng service account/SYSTEM được cài bằng installer elevated, kèm secret/ACL model riêng.

## Packaging evidence

Electron portable build từ ba binaries được rebuild trên PC theo source hiện tại đã thành công.

| Artifact | Kết quả |
|---|---:|
| Portable artifact | `SCP-DNA-Control-Center-1.6.0-portable.exe` |
| Size | `382,992,731` bytes |
| SHA-256 | `3664B0DE4A493793CF7D3074D65AFDACB954EF828E1F3D9DAB4924E0D9941E80` |
| Embedded `scp-backend.exe` | Có |
| Embedded `scp-llm-bridge.exe` | Có |
| Embedded `scp-loop-scheduler.exe` | Có |
| Embedded live `data/` | Không |
| Embedded Python source | Không |
| Embedded `.env` | Không |

Runtime binaries được rebuild vào staging trước khi đóng gói; binary đang chạy trên PC được backup và restore atomic sau build. Binaries không được commit trực tiếp vào GitHub source vì kích thước lớn và chứa artifact nền tảng; release bundle phải mang manifest/hash riêng.

## `v13.db` và data boundary

`v13.db` vẫn là **runtime writable database**, không phải policy file bất biến. Các bảng telemetry như `question_events`, `question_log`, `healing_history` và `pending_reverification` có thể tăng khi backend hoạt động. `SCP_ENABLE_CLOSED_LOOP=0` chỉ khóa closed-loop policy promotion; nó không có nghĩa mọi telemetry writer đều bị tắt.

Vì vậy production operation phải coi hash drift của `v13.db` là expected runtime mutation cần audit, không dùng hash file đơn lẻ để kết luận policy mutation. Snapshot phải dùng SQLite backup API nhất quán, manifest atomic, `integrity_check`, table counts và hash snapshot. Không restore live DB khi writer còn chạy.

## Regression và release gates

Sandbox regression cuối sau các source patches: **81 pytest passed, 0 failed**. Desktop JavaScript syntax check: `main.cjs` và `preload.cjs` pass. Portable Electron build: pass. PC health checkpoint: bốn service ports listen và bốn HTTP checks `200`. AutoFix bounded deterministic apply: pass contract, complete trong 16 giây, không gọi LLM cho finding chưa có patch safe.

## Blocker còn lại trước khi gọi là Production phổ quát

| Mức | Giới hạn | Ý nghĩa |
|---|---|---|
| P0 release evidence | Chưa test installer trên PC Windows thứ hai | Chưa chứng minh clean-machine portability |
| P0 lifecycle | Watchdog hiện user-session, chưa pre-logon | Logoff/cold boot vẫn là khoảng trống |
| P1 trust | Portable artifact chưa có Authenticode publisher signature | Windows trust UX và provenance chưa hoàn chỉnh |
| P1 operations | Chưa chứng minh disk-full/log rotation/ledger write failure | Có thể mất audit evidence nếu storage cạn |
| P1 runtime | Live `v13.db` vẫn writable telemetry | Cần tách telemetry khỏi policy state nếu muốn immutable policy boundary |
| P1 AutoFix | Deterministic-only không tự xử lý bug phức tạp | Cần approval queue/LLM worker riêng có timeout, job ID, cancel và rollback |
| P2 resilience | Sleep/hibernate/provider outage dài chưa test đầy đủ | Chưa có evidence cho mọi interruption mode |
| P2 security | Không có bằng chứng SCP bắt được “tất cả” AI/con người attacks | Chỉ có coverage theo detectors/fixtures đã tồn tại |

## Quy trình rollback

Nếu release candidate có lỗi, trước hết tạo kill switch tại `.private-secrets\release-audit\scp-247\KILL`. Supervisor sẽ dừng child theo Job Object. Giữ lại task XML, supervisor backup, runtime binary backup và SQLite snapshot. Sau đó restore source/binaries bằng artifact backup, xóa `KILL` chỉ sau khi đã kiểm tra hash và start lại task. Không restore `v13.db` khi còn listener; phải dừng toàn bộ writers, restore snapshot qua SQLite-safe path, chạy integrity check và ghi manifest mới.

## GitHub state

Source và tests đã đồng bộ lên `GA-LAB`:

- `97967cd` — bounded deterministic AutoFix scan workload.
- `af34422` — production AutoFix deterministic-only boundary.
- `e46515d` — exclude live runtime data from desktop packaging.
- `0039e41` — desktop runtime release contract and portable tests.
- `d6b0b96` — truthful user-session recovery watchdog scope.

GitHub source HEAD được xác nhận là `97967cdac231cff239fdd5bbbf6ea5b6aa67be22` với working tree sạch trong sandbox clone.

## Kết luận cuối

SCP có thể được gọi là **release candidate đã reality-test trên một PC Windows cụ thể**. Có thể chạy nền trong phiên user với supervisor, Job Object, kill switch, watchdog user-session, closed-loop OFF và AutoFix deterministic-only bounded.

SCP **chưa được gọi là production phổ quát hoặc hoàn thiện tuyệt đối** cho đến khi có clean-machine test trên PC thứ hai, pre-logon service boundary, publisher signature, disk/log failure tests và LLM AutoFix worker có job lifecycle riêng. Đây là kết luận phù hợp với DNA #22: **PASS không đồng nghĩa TRUE ở ngoài phạm vi evidence**.
