# SCP Runtime Audit — 17/08/2026

## Kết luận điều hành

SCP **đang chạy một phần quan trọng trên PC thật**: dashboard, scheduler, Python backend và Ollama đều có listener và trả HTTP 200 trên route phù hợp; Scheduled Task Supervisor và public relay bridge đang ở trạng thái `Running`. Tuy nhiên, đây không phải bằng chứng để gọi SCP production-ready. Chuỗi AutoFix end-to-end, policy learning production, external truth, chaos/security full gate và reproducibility từ working tree sạch vẫn thiếu evidence.

> **Kết luận trạng thái: `CANDIDATE_NOT_PROVEN`.** Các service sống và test profile pass trong scope đã chạy. Các phần không có artifact/provenance được ghi `BLOCKED` hoặc `UNPROVEN`, không suy đoán thành PASS.

## Snapshot kiểm tra

| Trường | Giá trị |
|---|---|
| Máy | Windows PC chính của SCP |
| Thời điểm snapshot | 17/08/2026 UTC |
| Python runtime | 3.12.10 |
| Bun runtime | 1.3.14 |
| Local repository head lúc audit | `4e47add` (commit local telemetry) |
| GitHub `main` evidence branch | Đã có telemetry patch `3028fb2`; audit/update docs tiếp tục sau đó |
| Working tree PC | 76 mục dirty/untracked quan sát được |
| Secrets | Không đọc/ghi raw token, key, password hay giá trị `.env` |

## Service contract

| Service | Port thật | Route đã gọi | Quan sát | Verdict |
|---|---:|---|---|---|
| Dashboard Bun | 3000 | `/` | Listener tồn tại, HTTP 200 | VERIFIED at audit time |
| Loop scheduler | 3030 | `/` | Listener tồn tại, HTTP 200 | VERIFIED at audit time |
| Python backend | 8000 | `/health` | Listener tồn tại, HTTP 200 | VERIFIED at audit time |
| Ollama local | 11434 | `/api/tags` | Listener tồn tại, HTTP 200 | VERIFIED at audit time |
| `SCP-247-Supervisor` | n/a | Windows Task Scheduler | `Running` | VERIFIED at audit time |
| `SCP-Public-Relay-Bridge` | outbound-only | Windows Task Scheduler | `Running` | VERIFIED at audit time |

## Độ tin cậy của test

| Runner | Kết quả | Runtime thật? | Kết luận đúng phạm vi |
|---|---:|---|---|
| `python -m pytest -q` bằng SCP venv | 101 passed, 2 warnings | Chủ yếu unit/integration | PASS_WITHIN_SCOPE |
| `tests/run_reality_tests_portable.py` | 74/74 pass, 0 fail, 0 timeout | Có probe runtime theo các case runner thu thập | PASS_WITHIN_SCOPE |
| Evolution disabled-startup probe | `DISABLED_STARTUP_TERMINAL=PASS` | Có ghi event mới trong production data ledger, nhưng không chạy evolution | VERIFIED cho nhánh disabled duy nhất |
| Golden Ask đã có | `2 + 2 = 4`, `PASS`, `0.99` ở evidence trước đó | Backend thật | VERIFIED cho input toán an toàn duy nhất |

## Proof matrix

| Năng lực | Evidence hiện có | Trạng thái | Khoảng trống |
|---|---|---|---|
| Supervisor recovery | `UNMANAGED_HEALTHY`, port 8000 recovery và HTTP readiness từ evidence trước | VERIFIED trong failure case đã chạy | Không phủ network/lease/dashboard crash |
| Outbound public relay | Website hiển thị agent online và 4/4 service; bridge chỉ allow `ask` | VERIFIED trong Ask/heartbeat scope | Không có proof cho action khác vì cố ý không hỗ trợ |
| FastLearning staging timeout | Child hard-timeout đã trả `TIMEOUT`, không tạo active policy production | VERIFIED trong staging timeout scope | Không chứng minh learning quality/external truth |
| Evolution lifecycle khi tắt | Ledger event mới `started: DISABLED` | VERIFIED | Evolution production cycle không chạy |
| Policy handoff production | `data/active_policies.json` không tồn tại | BLOCKED by design | Cần candidate, schema, verifier, atomic promotion, rollback evidence |
| AutoFix deterministic end-to-end | Không có `data/autofix_runs.jsonl` tại audit | BLOCKED | Cần candidate→patch→test→verifier→artifact chain |
| Internet learning/connector SLA | Không có evidence SLA/fresh external call được redact | BLOCKED | Cần provenance, TTL, source policy, egress deny test |
| Desktop capability/mic/webcam | UI/code tồn tại nhưng không có permission reality run trong audit | UNPROVEN | Cần test browser với grant/deny/repeat toggle thật |
| Security full gate | Allowlist Ask, token hash/TTL/filter/RBAC có evidence trước | PARTIALLY VERIFIED | Thiếu deny, path, egress, injection, capability revoke sau patch |
| Reproducibility | Backup/audit artifact và GitHub commits có | CANDIDATE | PC working tree dirty/history lệch, không phải snapshot sạch |

## Phát hiện

| ID | Mức | Nhãn evidence | Quan sát | Tác động | Cách đóng |
|---|---|---|---|---|---|
| AUD-001 | BLOCKER | OBSERVED | Không có active policy production | Không thể nói learning đã điều khiển production | Staging candidate → validate → human-reviewed atomic promotion → rollback proof |
| AUD-002 | BLOCKER | OBSERVED | Không có AutoFix run ledger chain tại audit | Không thể đo patch success hoặc regression-free | Chạy một candidate deterministic trong clone/staging, lưu toàn bộ hashes và verifier output |
| AUD-003 | HIGH | OBSERVED | PC repo có 76 dirty/untracked mục và diverge history | Khó tái hiện/bảo đảm code chạy giống GitHub | Inventory + backup + merge có kiểm soát, không reset/rebase mù |
| AUD-004 | HIGH | OBSERVED | Parent `C:\Users\check\Downloads\.env` có dangerous flags active, repo-local `.env` có các flags cùng tên inactive | Dễ hiểu sai nguồn config; cần prove child process dùng safe source | Inspect sanitized child env/command contract và add source provenance ledger, không lộ value secret |
| AUD-005 | MEDIUM | UNPROVEN | Mic/webcam chưa có browser permission evidence | UI có thể không hoạt động trên browser/thiết bị cụ thể | Grant/deny/unsupported/repeat-toggle test thật có user-controlled permissions |
| AUD-006 | MEDIUM | UNPROVEN | Không có full chaos/security gate sau patch | Recovery/security coverage có blind spot | Chạy profile crash, timeout, egress deny, injection, revoke trong sandbox |

## Rollback và giới hạn

Patch telemetry có bản rollback tại `scp-audit\telemetry-terminal-20260817-191901\subsystem_telemetry.py.before`. Không thay đổi `.env` parent, không rotate provider key, không tạo active policy trong audit. Không thực hiện restart/kill/xóa log trong lúc audit.

Các service HTTP 200 là quan sát tại một thời điểm, không phải soak test 24/7. Các test PASS được gắn với runner và phạm vi nói trên; không dùng chúng để nói SCP bắt được mọi tấn công AI/con người.
