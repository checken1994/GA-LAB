# AutoFix deterministic worker

## Mục đích

Production loop của SCP chỉ nên **scan và enqueue**. Việc apply patch được thực hiện bởi process `scp-autofix-worker`, được supervisor quản lý trong cùng Windows Job Object. Worker không có đường gọi LLM/provider; khi recipe không match, precondition không khớp, policy gate không ghi được, verifier lỗi hoặc source hash thay đổi, job không được coi là fixed.

## Luồng vận hành

```text
bounded AST scan
  -> finding_id + source_hash
  -> SQLite queue: queued
  -> worker lease: running
  -> AST patch recipe
  -> policy gate + audit-chain check
  -> candidate / rejected / atomic apply
  -> parse + rescan + recipe postcondition
  -> audit + rollback token
  -> applied hoặc rolled_back/failed
```

`queued`, `running`, `candidate`, `rejected`, `applied`, `rolled_back`, `failed`, `expired` và `cancelled` là các trạng thái khác nhau. `HTTP 200` của `/v105/autofix/run-audit` ở worker mode chỉ có nghĩa scan/enqueue hoàn tất; nó **không** có nghĩa patch đã được apply. Trạng thái thật xem qua `/v105/autofix/worker/status` và `/v105/autofix/worker/jobs/{job_id}`.

## Cấu hình production khuyến nghị

Các biến dưới đây được đặt trong `child-safe.env` hoặc được supervisor truyền trực tiếp; không đặt secrets inline trong source repository.

```dotenv
SCP_AUTOFIX_MODE=apply
SCP_AUTOFIX_DETERMINISTIC_ONLY=1
SCP_AUTOFIX_WORKER_MODE=deterministic
SCP_AUTOFIX_MAX_SCAN_FILES=50
SCP_MAX_AUDIT_BUGS=5
SCP_AUTOFIX_DETERMINISTIC_MAX_RISK=low

SCP_AUTOFIX_WORKER_ENABLED=1
SCP_AUTOFIX_WORKER_MAX_JOBS=1
SCP_AUTOFIX_WORKER_MAX_RETRIES=2
SCP_AUTOFIX_WORKER_LEASE_SECONDS=180
SCP_AUTOFIX_WORKER_JOB_TIMEOUT_SECONDS=120
SCP_AUTOFIX_WORKER_POLL_SECONDS=30
SCP_AUTOFIX_WORKER_MAX_FILES=5
SCP_AUTOFIX_WORKER_AUTO_APPLY_RISK=low
SCP_AUTOFIX_WORKER_REQUIRE_BASELINE=1
SCP_AUTOFIX_WORKER_REQUIRE_TESTS=0
SCP_AUTOFIX_WORKER_ALLOW_NETWORK=0
SCP_AUTOFIX_WORKER_ALLOW_LLM=0

SCP_ENABLE_CLOSED_LOOP=0
SCP_AUTO_APPROVE_TIER3=0
SCP_TIER3_ALLOW_RELAXATION=0
SCP_TIER3_ALLOW_BAREEXCEPTPASS=0
```

`SCP_AUTOFIX_WORKER_AUTO_APPLY_RISK=low` là baseline. Có thể nâng lên `medium` chỉ sau khi recipe tương ứng đã có fixture, targeted tests, rollback test và evidence trên đúng codebase. Không dùng `high` trong unattended mode.

## Patch deterministic hiện có

Worker hiện có các recipe AST-aware sau:

| Patch ID | Finding | Risk | Hành vi |
|---|---|---:|---|
| `bare_except_pass_ast_v1` | `BareExceptPass`, một `ExceptHandler` chỉ chứa `pass` | Low | Thêm binding exception nếu thiếu và ghi log qua logger đã tồn tại |
| `open_encoding_ast_v1` | `MissingEncoding` trên `open()` dạng text đơn giản | Low | Thêm `encoding="utf-8"`; loại binary/opener/shape mơ hồ |
| `sql_parameterize_ast_v1` | SQL f-string với value là simple name trong `WHERE`/`VALUES` | Medium | Chuyển value interpolation thành placeholder + tuple; reject identifier interpolation, nested expression và multi-statement |

Các fixer cũ như `add_null_check`, `add_lock`, `fix_type_mismatch`, `add_context_manager` vẫn là candidate surface hẹp. Không nên tự động dùng chúng chỉ vì pattern text khớp; nhiều fixer có thể đổi semantics hoặc lifecycle. Worker mới mặc định chỉ apply recipe low-risk.

## Cách nâng một patch phức tạp

Mỗi recipe mới phải có version bất biến và đủ năm phần. Thứ nhất, `match()` phải dùng AST/data-flow local và reject mọi shape không chứng minh được. Thứ hai, `build()` chỉ trả candidate source, không ghi file, không gọi network. Thứ ba, candidate phải có risk và preconditions gồm source hash, allowed root, protected-path check và bug type. Thứ tư, postcondition phải kiểm tra AST parse, finding cũ biến mất và không sinh forbidden pattern mới. Thứ năm, fixture phải chứng minh apply lần hai không tạo diff mới, hash mismatch bị từ chối, verifier failure rollback atomic và worker restart không duplicate apply.

Một patch có thay đổi control-flow, default value, auth/threshold, locking lifecycle, database semantics hoặc policy decision không nên auto-apply chỉ nhờ AST parse. Recipe đó nên dừng ở `candidate` và chờ approval/test contract.

## Vận hành và kiểm tra

Kiểm tra worker process nằm trong supervisor Job Object, có `SCP_AUTOFIX_WORKER_ALLOW_LLM=0`, không có network call trong worker và chỉ có một lease đang chạy. Kiểm tra queue bằng endpoint admin; không dựa vào trường `last_run` của scheduler để kết luận apply thành công.

Rollback dùng token trong `data/rollback_tokens.json` và kiểm tra hash hiện tại trước khi restore. Restore là atomic bằng temp file, `fsync` và `os.replace`. Nếu file đã bị sửa sau patch, rollback thường bị từ chối để không ghi đè thay đổi mới; chỉ operator mới được chọn force rollback.

## Giới hạn còn lại

AST-aware không đồng nghĩa semantic correctness toàn hệ thống. SQL recipe mới chỉ an toàn cho profile shape hẹp, không chứng minh driver-specific behavior ngoài fixture. Worker chưa tự động xử lý logic flow, null default, race lifecycle hay auth policy; các vùng đó phải chuyển qua candidate/review hoặc một test contract mạnh hơn. Mục tiêu là **mở rộng deterministic coverage có chứng cứ**, không biến “không gọi LLM” thành lý do để nới lỏng safety gate.
