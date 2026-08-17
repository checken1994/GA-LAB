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

## Child runtime guardrails

Runtime file `.private-secrets/release-audit/scp-247/child-safe.env` do Supervisor tạo có các guardrail sau ở trạng thái `OFF`: `SCP_DEV_MODE`, `SCP_SKIP_STARTUP_GATE`, `SCP_AUTO_APPROVE_TIER3`, `SCP_TIER3_ALLOW_RELAXATION`, `SCP_TIER3_ALLOW_BAREEXCEPTPASS`, `SCP_ENABLE_CLOSED_LOOP`, `SCP_EVOLUTION_AUTO`, `SCP_WHY_LLM_ENABLED`. `SCP_AUTOFIX_DETERMINISTIC_ONLY` ở `ON`.

Điều này chứng minh **child process đang chạy không nhận các cờ nguy hiểm đó**. Nó không nói rằng parent `.env` không có cờ cũ, và không tự biến policy production thành active.

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
| Policy handoff production | Staging snapshot có 91 experience nhưng 0 lesson thuộc supported taxonomy; `data/active_policies.json` không tồn tại | BLOCKED by design | Cần lesson có action/target/value/provenance; không ép verdict history thành policy |
| AutoFix deterministic fixture end-to-end | Private XSS fixture đã preview→policy-deny→apply→rollback hash đúng sau patch Windows line-ending | VERIFIED in staging | Cần candidate production-like riêng; fixture không chứng minh mọi file/bug/LLM patch |
| Internet learning/connector SLA | Không có evidence SLA/fresh external call được redact | BLOCKED | Cần provenance, TTL, source policy, egress deny test |
| Desktop capability/mic/webcam | Edge PC: Windows thấy XWF-1080P/microphone `OK`, consent `Allow`; user xác nhận Camera và Voice input hoạt động sau refresh | PARTIALLY VERIFIED | Cần evidence start/stop chu kỳ thứ hai và screenshot/error thật nếu failure quay lại |
| Security full gate | Allowlist Ask, token hash/TTL/filter/RBAC có evidence trước | PARTIALLY VERIFIED | Thiếu deny, path, egress, injection, capability revoke sau patch |
| Reproducibility | Backup/audit artifact và GitHub commits có | CANDIDATE | PC working tree dirty/history lệch, không phải snapshot sạch |

## Phát hiện

| ID | Mức | Nhãn evidence | Quan sát | Tác động | Cách đóng |
|---|---|---|---|---|---|
| AUD-001 | BLOCKER | OBSERVED | Không có active policy production; 91 experience staging đều không có taxonomy policy hợp lệ | Không thể nói learning đã điều khiển production | Tạo lesson có action/target/value/provenance → validate → human-reviewed atomic promotion → rollback proof |
| AUD-002 | HIGH | PARTIALLY_CLOSED | AutoFix deterministic private fixture có apply/rollback evidence; production ledger chain vẫn chưa có | Không được suy diễn coverage mọi source/bug | Chạy candidate production-like trong clone/staging, lưu hashes, verifier và rollback artifact |
| AUD-003 | HIGH | OBSERVED | PC repo có 76 dirty/untracked mục và diverge history | Khó tái hiện/bảo đảm code chạy giống GitHub | Inventory + backup + merge có kiểm soát, không reset/rebase mù |
| AUD-004 | MEDIUM | PARTIALLY_CLOSED | Parent `.env` có thể có cờ legacy, nhưng actual Supervisor child-safe env tắt 8 guardrail nguy hiểm và giới hạn AutoFix deterministic | Cần tiếp tục nguồn-config provenance; không dùng parent env để suy luận runtime child | Giữ child-safe env là boundary duy nhất, thêm provenance ledger không lộ secret |
| AUD-005 | MEDIUM | PARTIALLY_CLOSED | Edge PC đã dùng Camera/Voice input theo user, Windows device/consent precondition đạt | Chưa có repeat-toggle full proof hoặc artifact preview | Ghi evidence start/stop chu kỳ hai; nếu failure, lưu exact browser error |
| AUD-006 | MEDIUM | UNPROVEN | Không có full chaos/security gate sau patch | Recovery/security coverage có blind spot | Chạy profile crash, timeout, egress deny, injection, revoke trong sandbox |

## Rollback và giới hạn

Patch telemetry có bản rollback tại `scp-audit\telemetry-terminal-20260817-191901\subsystem_telemetry.py.before`. Không thay đổi `.env` parent, không rotate provider key, không tạo active policy trong audit. Không thực hiện restart/kill/xóa log trong lúc audit.

Các service HTTP 200 là quan sát tại một thời điểm, không phải soak test 24/7. Các test PASS được gắn với runner và phạm vi nói trên; không dùng chúng để nói SCP bắt được mọi tấn công AI/con người.
