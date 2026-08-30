# SCP Release Evidence Gate — Kernel/Recovery/Security Candidate

## Kết luận điều hành

Trong isolated test copy, SCP đã được bổ sung một **Task Kernel durable candidate** với SQLite WAL, event journal hash-chain, state machine có transition guard, lease TTL/heartbeat/fencing, checkpoint hash, logical idempotency, verifier độc lập, recovery decision và kill switch. Các acceptance suite local, Kernel API smoke trên port 8003, process-crash recovery, journal tamper detection, capability guard, workspace/egress guard, trace ledger và local latency đều đã có evidence quan sát được.

Tuy nhiên bản này **chưa phải release production và chưa phải Agent OS đã chứng minh end-to-end**. Kernel API chỉ chạy riêng trên isolated port 8003 rồi đã clean stop; `/ask` hiện tại chưa được nối vào Kernel. Chưa có OS-level sandbox proof, real provider/network chaos, multi-process journal contention, full-stack clean start/stop và release snapshot có git/lock reproducibility sạch. Vì một số gate bắt buộc còn thiếu, verdict đúng là **CANDIDATE_NOT_PROVEN / RELEASE_BLOCKED**.

> PASS của một test chỉ có nghĩa là không phát hiện lỗi trong workload và phạm vi đó. Nó không chứng minh SCP production đã an toàn hoặc có thể xử lý mọi bài thi.

## Release identity và phạm vi

| Trường | Giá trị |
|---|---|
| Scope | `D:\scp-local-agent\workspace\scp-phase1-test` |
| Production | Port 8000, PID 25212 — không sửa, không restart |
| Test | Port 8001, PID 14184 — không sửa, không restart |
| Isolated backend | Port 8000, PID 29364 — giữ nguyên |
| Kernel API adapter | Port 8003, PID 29528 trong smoke test — đã clean stop |
| Backend commit quan sát được | `4e47add244edadfc1eb53baa4f75ebf239a75e82` |
| RAG 1.000 câu | Đóng băng; không human review trong phase này |
| Release label | `candidate-task-kernel-v1` |

## Gate matrix

| Gate | Trạng thái | Evidence | Khoảng trống |
|---|---|---|---|
| Config | `PASS_WITHIN_SCOPE` | Kernel DB riêng, readiness trả `journal_authoritative=true`, production protected | Chưa có service manifest release đầy đủ cho toàn stack |
| Static | `PASS_WITHIN_SCOPE` | Compile pass cho Kernel, verifier, recovery, capability, sandbox, trace và tests | Chưa có clean git working tree/lock snapshot trong isolated copy |
| Runtime | `PASS_WITHIN_SCOPE` | 8000/8001/8000 health đúng PID; 8003 readiness và HTTP smoke pass; 8003 clean stop | Chưa clean start/stop toàn bộ stack từ manifest |
| Kernel acceptance | `PASS_WITHIN_SCOPE` | 12 tests pass, gồm lease, fencing, journal, replay, checkpoint, idempotency, restart, kill và verifier commit | Chưa multi-process DB contention |
| Verifier | `PASS_WITHIN_SCOPE` | 5 tests pass: VERIFIED, CONTRADICTED, INSUFFICIENT, UNKNOWN và evidence gate | Chưa gắn vào `/ask` production-like flow |
| Recovery/chaos | `PASS_WITHIN_SCOPE` | 4 recovery tests; worker crash sau checkpoint chuyển RECONCILING; retry mù bị chặn; journal tamper bị phát hiện | Chưa provider timeout/network/browser/dashboard chaos thật |
| Security | `PASS_WITHIN_SCOPE` | Capability 5 tests; sandbox/egress 3 tests; revoke/global kill/path traversal/secret path/private IP deny | Đây là application guard, chưa đủ OS/runtime sandbox proof |
| Observability | `PASS_WITHIN_SCOPE` | Trace ledger 3 tests, correlation IDs, hash chain, secret redaction | Chưa nối toàn bộ request→/ask→Kernel→tool→verifier trace |
| Latency | `PASS_WITHIN_SCOPE` | 100 local Kernel operations: p50 4.364 ms, p95 4.824 ms, p99 7.2345 ms | Không đại diện `/ask`, Ollama, retrieval hoặc full provider latency |
| Golden task | `PASS_WITHIN_SCOPE` | Golden RAG 3/3 replay trước đó trên isolated 8000 | Golden chưa đi xuyên Kernel API mới |
| Reproducibility | `BLOCKED` | Hash artifact/test logs có lưu | Isolated copy không có `.git`; chưa có clean lock/rebuild evidence |
| Rollback | `CANDIDATE` | Backup manifest và `api_server.py.pre-task-kernel` tồn tại | Chưa diễn tập rollback/restore hoàn chỉnh |
| Full RAG 1.000 | `BLOCKED` | Candidate artifact đã đóng băng | Gold độc lập, Ragas/ARES full và review queue chưa hoàn tất |

## Acceptance evidence summary

| Nhóm | Kết quả |
|---|---:|
| Task Kernel tests | 12/12 PASS |
| Verifier tests | 5/5 PASS |
| Recovery tests | 4/4 PASS |
| Capability tests | 5/5 PASS |
| Workspace/egress tests | 3/3 PASS |
| Trace ledger tests | 3/3 PASS |
| Process-crash chaos | PASS_WITHIN_SCOPE |
| Journal tamper detection | PASS_WITHIN_SCOPE |
| Kernel API HTTP smoke | PASS_WITHIN_SCOPE |
| Tổng acceptance tests | 32 PASS |

Các con số trên là evidence trong isolated workload, **không phải điểm chất lượng RAG và không phải chứng nhận production**.

## Safety invariants đã quan sát

`policy_bypass_count=0`, `duplicate_side_effect_count=0`, `cleanup_failure_count=0` trong local harness. Khi worker chết sau action dispatch, state chuyển sang `RECONCILING`, `safe_to_retry=false`, cần `provider_request_status` và `read_only_state`; không retry side effect mù. Khi global kill bật, lease cũ bị stale và claim mới bị deny. Khi journal bị sửa hash, verifier phát hiện `hash_chain_valid=false`.

## Rollback

Rollback phase này không cần chạm production. Có backup manifest tại `reports/phase4_task_kernel_backup_manifest.json` và backup `api_server.py` trước task-kernel. Các file mới của candidate gồm `scp/task_kernel.py`, `scp/verifier.py`, `scp/recovery_manager.py`, `scp/capability_guard.py`, `scp/sandbox_guards.py`, `scp/trace_ledger.py`, `scp/kernel_api.py` và các test/scripts tương ứng. Rollback logic là clean stop adapter nếu còn chạy, xóa/đổi tên các file candidate và khôi phục backup nếu có file cũ bị thay; hiện chưa gọi đây là rollback đã diễn tập vì chưa chạy restore drill đầy đủ.

## Điều kiện để đổi verdict

Để đổi từ `RELEASE_BLOCKED` sang `CANDIDATE` cần nối Kernel vào test runtime 8000 bằng adapter nhỏ có backup, chạy golden task xuyên request→Kernel→verifier→audit, bổ sung multi-process journal contention và clean start/readiness/clean stop. Để đổi sang `PASS` trong một scope cụ thể cần thêm OS sandbox/egress evidence, provider/network chaos, reproducibility snapshot sạch, rollback drill và tất cả gate bắt buộc đạt. Mục tiêu RAG 1.000 vẫn là một gate riêng: phải chờ gold được review, rồi mới chạy Ragas/ARES chuẩn.

## Final verdict

**`RELEASE_BLOCKED` — `CANDIDATE_NOT_PROVEN`.**

Phần còn thiếu của SCP đã được bổ sung thành candidate có test và evidence local, nhưng chưa đủ bằng chứng để gọi SCP là Agent OS production-ready hoặc tuyên bố đã hoàn thành mục tiêu trả lời 1.000 câu RAG.

## Evidence files

| File | Vai trò |
|---|---|
| `reports/phase4_kernel_gap_matrix_v1.md` | Gap matrix trước khi sửa |
| `reports/phase4_runtime_audit_v1.json` | Runtime audit 8000/8001/8000/dependencies |
| `reports/task-kernel-contract-v1.md` | Contract Kernel |
| `reports/phase4_task_kernel_evidence_v2.json` | Kernel acceptance evidence |
| `reports/phase4_security_recovery_evidence_v1.json` | Verifier/recovery/security evidence |
| `reports/phase5_kernel_chaos_latency_v1.json` | Chaos và local latency |
| `reports/phase5_security_chaos_latency_evidence_v1.json` | Consolidated phase 5 evidence |
| `reports/phase4_kernel_api_smoke_8003.json` | HTTP smoke Kernel API |
| `reports/phase6_release_evidence_gate_v1.json` | Manifest machine-readable |

## References

[1] `Blueprint SCP Agent OS.md` — contract về control plane, Task Kernel, capability, recovery và verifier.

[2] `SCP_BUILD_PLAN_4_PILLARS_AND_RAG_2026-08-18.md` — thứ tự triển khai và điều kiện release gate.

[3] `scp-release-evidence-gate/SKILL.md` — quy tắc không nâng PASS cục bộ thành release PASS.

[4] `scp-reality-verifier/SKILL.md` — phân biệt static, integration, end-to-end và recovery proof.
