# SCP — Báo cáo trạng thái sau khi hoàn thiện phần còn thiếu

## Kết luận

Phần thiếu lớn nhất của SCP — **Task Kernel durable, verifier, recovery, capability guard, sandbox/egress guard, observability và acceptance evidence** — đã được bổ sung và chạy thật trên **isolated backend 8002**. Kernel đã được nối vào backend 8002 bằng router riêng `/v1/kernel`, có DB SQLite WAL riêng, backup trước patch và đã chạy golden task xuyên HTTP.

Kết quả E2E quan sát được: một task local đi qua `CREATED → PLANNING → READY → QUEUED → LEASED → RUNNING → WAITING_TOOL → VERIFYING → COMPLETED`; checkpoint được ghi trước boundary; verifier độc lập trả `VERIFIED` với evidence reference; Kernel commit được `COMPLETED`; event journal có 10 event và event cuối là `TASK_COMPLETED`. Một task khác mô phỏng `LOST_RESPONSE` sau action dispatch đã chuyển sang `RECONCILING`, `safe_to_retry=false`, không retry mù.

Đây là **runtime proof trong phạm vi Kernel candidate trên isolated 8002**, chưa phải tuyên bố SCP production-ready và chưa phải bằng chứng RAG 1.000 câu.

## Bằng chứng chính

| Hạng mục | Kết quả |
|---|---|
| Task Kernel acceptance | 12/12 PASS |
| Verifier acceptance | 5/5 PASS |
| Recovery acceptance | 4/4 PASS |
| Capability acceptance | 5/5 PASS |
| Workspace/egress acceptance | 3/3 PASS |
| Trace ledger acceptance | 3/3 PASS |
| Tổng local acceptance | 32 PASS |
| Golden E2E qua HTTP 8002 | `PASS_WITHIN_SCOPE` |
| Golden task cuối | `COMPLETED`, verifier `VERIFIED`, evidence có thật |
| Lost-response recovery | `RECONCILING`, `safe_to_retry=false` |
| Multi-process lease contention | 4 worker, đúng 1 lease, 3 conflict |
| Journal contention | Hash chain hợp lệ |
| Rollback drill | Restore hash chính xác |
| Local Kernel latency | p50 4.364 ms, p95 4.824 ms, p99 7.2345 ms trên 100 local operations |

## Runtime safety

| Service | PID | Trạng thái |
|---|---:|---|
| Production 8000 | 25212 | `mode=production`, health `ok`, không sửa |
| Test 8001 | 14184 | `mode=test`, health `ok`, không restart |
| Isolated 8002 | 18656 | `mode=test`, health `ok`, Kernel readiness `ready` |

Kernel adapter 8003 trước đó đã được chạy smoke test và clean stop. Kernel router hiện được nối trực tiếp vào isolated 8002, không dùng 8003 cho release.

## Thành phần đã bổ sung

`scp/task_kernel.py` cung cấp state machine, SQLite WAL, append-only event journal hash-chain, projection rebuild, lease TTL/heartbeat/fencing, `STALE_LEASE`, checkpoint hash, idempotency key, global/task kill switch và completion gate.

`scp/verifier.py` kiểm tra postcondition quan sát được với các verdict `VERIFIED`, `CONTRADICTED`, `INSUFFICIENT` và `UNKNOWN`. Kernel chỉ commit `COMPLETED` khi có verifier identity, verdict `VERIFIED` và evidence reference.

`scp/recovery_manager.py` phân biệt transient retry, reconcile sau mất response, policy/integrity failure và human review. `scp/capability_guard.py` kiểm tra quyền theo task, attempt, tool, resource, operation, expiry, max uses, revocation epoch và policy hash. `scp/sandbox_guards.py` chặn path traversal, secret/config path, private IP egress, domain ngoài allowlist và external write không có approval. `scp/trace_ledger.py` ghi correlation IDs, hash-chain và redact secret.

## Các điểm vẫn chưa được phép gọi là hoàn tất

| Khoảng trống | Trạng thái |
|---|---|
| Nối Kernel vào `/ask` RAG hiện tại | Chưa làm; mới có `/v1/kernel` adapter trên 8002 |
| OS-level sandbox cho toàn bộ child process/browser/MCP | Chưa có evidence runtime |
| Egress proxy thật và provider/network chaos | Chưa chạy; hiện mới có application guard |
| Clean start/stop toàn bộ stack bằng release manifest | Chưa chạy đủ |
| Git/lockfile reproducibility sạch của isolated copy | Chưa đủ; bản copy không có `.git` |
| Rollback live service | Mới diễn tập temp-copy restore, chưa rollback live |
| RAG 1.000 câu, gold độc lập, Ragas/ARES full | Đóng băng theo yêu cầu; vẫn `BLOCKED` |

## Verdict thật

**Kernel/Recovery candidate trên isolated 8002: `RUNTIME_PROVEN_WITHIN_SCOPE`.**

**SCP tổng thể production/Agent OS: `CANDIDATE_NOT_PROVEN`.**

**Release gate: `BLOCKED`.**

Không có cơ sở để nói SCP đã hoàn thành mục tiêu trả lời toàn bộ 1.000 câu RAG. File 1.000 câu đã được để riêng; người dùng có thể xử lý sau như đã yêu cầu.

## File evidence quan trọng

| File | Nội dung |
|---|---|
| `reports/phase7_kernel_e2e_golden_result.json` | Golden E2E qua HTTP 8002 |
| `reports/phase9_repro_rollback_result.json` | Multi-process contention và rollback drill |
| `reports/phase6_release_evidence_gate_v1.json` | Release manifest/hash |
| `reports/phase5_full_acceptance.log` | 32 acceptance tests |
| `reports/phase4_kernel_router_patch_manifest.json` | Backup/hash patch api_server isolated |
| `reports/task-kernel-contract-v1.md` | Contract Kernel |
| `reports/SCP_PHASE4_6_RELEASE_EVIDENCE_GATE.md` | Gate report chi tiết |

## References

[1] `Blueprint SCP Agent OS.md` — Task Kernel, lease, recovery, verifier, capability và kill switch.

[2] `SCP_BUILD_PLAN_4_PILLARS_AND_RAG_2026-08-18.md` — thứ tự triển khai và release gate.

[3] `scp-reality-verifier/SKILL.md` — yêu cầu postcondition và phân biệt runtime proof với static PASS.

[4] `scp-release-evidence-gate/SKILL.md` — gate thiếu evidence phải giữ `BLOCKED`.
