# SCP Release Evidence Gate — 17/08/2026

## Danh tính kiểm tra

| Trường | Giá trị |
|---|---|
| Base commit trước các patch trong working tree | `5dca3f9a1d72d8d41b2232c0265df30f38516b88` |
| GitHub evidence sau đối chiếu | `3028fb2` (telemetry terminal) và `a927a0d` (evidence report) |
| Máy kiểm tra runtime | Windows PC chính của SCP |
| Runtime local kiểm tra | dashboard `3000`, scheduler `3030`, backend `8000`, Ollama `11434` |
| Profile test | portable reality tests + Ask thực + recovery Supervisor + staging timeout |
| Secrets | Không ghi token, URL private hoặc `.env` vào report |

## Kết quả gate

| Gate | Trạng thái | Evidence quan sát | Giới hạn |
|---|---|---|---|
| Static patch | PASS_WITHIN_SCOPE | `git diff --check`; `py_compile` cho `api_server.py`, `bounded_evolution.py`, runner staging | Không chứng minh semantic mọi đường code |
| Reality harness | PASS_WITHIN_SCOPE | `74/74` PASS, `0` fail, `0` timeout, exit `0` trên PC | Bộ harness không phủ toàn bộ workload production |
| Python regression | PASS_WITHIN_SCOPE | `101 passed`, `2 warnings` bằng venv SCP sau patch telemetry | Test collection không thay cho chaos/security/E2E proof |
| Runtime readiness | VERIFIED | Bốn HTTP probe `200` sau restart Supervisor | Không phải soak test dài ngày |
| Ask golden task | VERIFIED | `/ask` thật trả `final_answer=2 + 2 = 4`, `verdict=PASS`, `confidence=0.99`, `run_status=SUCCESS`; field `answer` không tồn tại | Một input toán an toàn, không đại diện mọi domain |
| Supervisor recovery | VERIFIED | Với backend ngoài Job Object, ledger có `UNMANAGED_HEALTHY`; sau khi listener biến mất Supervisor lấy lại port `8000`; full stack lại `200` | Không kiểm thử mọi crash/lease/network failure |
| Ollama prerequisite | VERIFIED | Supervisor nạp được Ollama local và full stack đạt `200` sau controlled restart | Chưa là Windows Service độc lập |
| Ledger writer | VERIFIED | Writer dùng một JSON line/event; audit không còn cần suy luận qua dòng trống mới | Ledger lịch sử cũ chưa được dùng làm proof mới |
| Evolution disabled lifecycle | VERIFIED | Child probe `SCP_EVOLUTION_ENABLED=0` ghi event `started` với terminal `DISABLED` trong `data/evolution_runs.jsonl` | Chỉ chứng minh nhánh disabled; không chạy `evolve_cycle`, AutoFix hoặc policy promotion |
| Evolution staging timeout | VERIFIED | Provider staging 10 giây trả manifest `TIMEOUT`, `completed_at` có mặt, không còn child process, không tạo active policy production | Evolution production ledger cũ vẫn chỉ có `STARTING` |
| Policy handoff production | BLOCKED | `data/active_policies.json` không tồn tại trên PC production | Không được tự đưa policy học được vào active policy chỉ vì staging pass |
| AutoFix candidate→patch→regression | BLOCKED | Có scanner/telemetry nhưng chưa có chuỗi evidence production đầy đủ | Không gọi AutoFix hoàn thiện |
| Security full gate | BLOCKED | Relay có token hash, allowlist Ask, TTL, result filtering và RBAC website | Chưa chạy toàn bộ deny/egress/prompt-injection/capability-revoke profile sau patch |
| Reproducibility | CANDIDATE | Backup trước mỗi patch PC, audit directories và code source có patch tương ứng | Working tree PC còn nhiều thay đổi cũ/không liên quan; chưa phải snapshot sạch |

## Patch đã kiểm chứng

| Thành phần | Thay đổi | Rollback PC |
|---|---|---|
| `scripts/ops/scp_247_supervisor.ps1` | Auto-start Ollama, reset circuit sau recovery, writer JSONL một dòng, bind `PYTHONPATH`, nhận biết listener khỏe ngoài Job Object | Các file `.before` trong `scp-audit\supervisor-*` |
| `scp/core/bounded_evolution.py` | Parent ghi terminal event cho success/failure/timeout | Backup file trước patch trong thư mục audit |
| `scripts/learning/learning_staging_r43.py` | Provider staging chạy child process có hard timeout | Các file `.before` trong `scp-audit\learning-staging-*` |
| `scp/api_server.py` | Health detailed có marker route không nhạy cảm để quan sát runtime | Backup API trước patch trong audit |
| `scp/core/subsystem_telemetry.py` | Startup có policy `disabled` ghi terminal `DISABLED` thay vì `STARTING` không có điểm kết thúc | `scp-audit\telemetry-terminal-20260817-191901\subsystem_telemetry.py.before` |

## Verdict

> **CANDIDATE_NOT_PROVEN.** Các thay đổi nêu trên có bằng chứng trong profile đã chạy. Điều đó không chứng minh SCP đã production-ready hoàn toàn, chưa nói tới mục tiêu “bắt được tất cả cuộc tấn công AI + con người”. Hai blocker rõ nhất là **policy handoff production** và **AutoFix end-to-end có regression evidence**. Security/chaos/soak test toàn diện cũng còn thiếu.

PC runtime có logic telemetry tương đương với GitHub, nhưng local repo trên PC có local commit riêng, history cũ và nhiều file dirty. Không rebase/pull/reset tự động trong audit này; làm vậy có thể đè source chưa phân loại. Vì vậy GitHub và PC chưa có reproducibility proof hoàn chỉnh.

## Bước an toàn tiếp theo

1. Giữ policy production inactive cho đến khi có schema, verifier độc lập và rollback evidence cho một candidate policy cụ thể.
2. Tạo một AutoFix candidate an toàn ở staging, chứng minh candidate → patch → regression-free → ledger terminal trước khi cho phép bất kỳ action production nào.
3. Chạy release gate lại từ working tree sạch sau khi commit các patch đã xác minh.
