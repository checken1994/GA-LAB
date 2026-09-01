# BƯỚC 0 — BASELINE & EXECUTION RECORD (2026-09-02)

Freeze inventory theo `scp-execution-order-master-plan` (0.1). Snapshot khi bắt đầu phiên: HEAD `a545e69e3186460c4555accdf489460c25d2d8e6` (local), Python 3.12.10, Windows, pytest basetemp `reports/pytest-basetemp`.

## 0.1 Baseline trước khi sửa
- Collect: pytest collect OK (không error); focused T00/T07/T09/T10/T11 trước sửa: 42 passed / 9 failed (phần lớn HARNESS_BROKEN do module giả + T00 chưa có meta-tests).
- Defects đã biết trước phiên: 2 module giả trong production (đã xóa), mixin rate-limit `>= 50` (NameError latent + regression 200→50).

## Product defects PHÁT HIỆN + ĐÃ SỬA trong Bước 0 (tại điểm lỗi, minimal patch)
1. **Generic AutoFix apply path đã là dead code**: `_auto_fix_part3` dùng `filepath` và `agent` chỉ được định nghĩa trong `_auto_fix_part1` → 2 lớp NameError → realtime-verifier fail-closed chặn MỌI generic SEARCH/REPLACE fix ("realtime verifier failed; fix is UNVERIFIED"). Chỉ đường XSS deterministic còn sống. Đã bind `filepath = Path(ctx.bug.file)` + tái tạo `agent` (same pattern part1). **Phát hiện bởi T09 Golden B — đúng mục đích của harness.**
2. **Commit leg của AutoFix chết 100% (chưa sửa — PRODUCT_BLOCKED)**: `scp/autofix/runner_phases/reality_test.py` KHÔNG tồn tại → Phase B của `run_full_post_fix_verify` luôn ImportError → mọi fix apply xong đều UNVERIFIED → rollback + escalate Tier 3 (fail-closed, an toàn). Cần: (1) implement reality_test, (2) gold-seeding policy cho evidence_replay, (3) semantic_equiv backup ghi lúc apply. Khóa bởi test `test_golden_b_verified_fix_commits_to_durable_state` (RED có chủ ý).
3. **Rollback mất line-ending (5 điểm)**: restore dùng `write_text(..., encoding="utf-8")` không `newline=""` → LF→CRLF trên Windows, hash sau-rollback lệch (chính class bug engine đã note ở phần backup nhưng bỏ sót phần restore). Đã sửa cả 5 điểm.
4. **WebSocket auth fallback (chat.py:111)**: `session_id` được dùng làm token dự phòng "dev UI" — session_id do client kiểm soát. Đã bỏ fallback: chỉ nhận `token` query param tường minh (fail-closed). Không có test nào phụ thuộc fallback (verified by grep).
5. **Benchmark ước lượng đội lốt benchmark thật (v104_routes.py:365)**: `sequential = 50 × 700ms` hằng số, trả về `speedup_factor` như measured. Đã thêm `measurement_kind: "ESTIMATE"` + note cấm dùng làm performance gate (0.12: ESTIMATE ≠ BENCHMARK; benchmark thật là việc còn lại).

## Test harness T00–T11 trạng thái sau Bước 0
- **T00**: +3 meta-test (zero-collected; bare `scp.*` import phải resolve tới module+symbol thật — try-guarded là pattern BLOCKED hợp lệ; cấm `pytest.main` + cấm git commit/reset không isolation marker). Bắt được 2 violation thật: `tests/T05_gateway/test_provider_fallback.py` zero-collected (đã wire thành pytest test thật) và import kiểu `from pkg import submodule` (sai ngữ nghĩa check đầu tiên — đã sửa logic check).
- **T07**: recall/precision scanner thật (BareExceptPass) + verifier verdicts thật → PASS; missing-piece discovery → **RED `PRODUCT_BLOCKED`** (chỉ tới `scp.meta.epistemic_boundary` chưa tồn tại; cấm stub).
- **T09 Golden A**: real path TaskKernelHandsBridge + HandsExecutor + PCController(tmp workspace) + IndependentVerifier artifact_hash (VERIFIED + tampered CONTRADICTED) + idempotency replay → PASS.
- **T09 Golden B**: compose thật (ast_scan → BugReportValidator [probe thực nghiệm: KEEP BareExceptPass, DROP NullDereference] → SEARCH/REPLACE → full gate stack → IMP-1 post-fix verify). Fail-closed rollback + escalate proven → PASS; cosmetic never promoted → PASS; security-weakening patch bị policy gate KILL → PASS; commit leg → **RED `PRODUCT_BLOCKED`** (reality_test module).
- **T10**: 2 boundary hard-kill thật (child process + checkpoint WAITING_TOOL → RECOVERING; RUNNING no-checkpoint → HUMAN_REVIEW) + journal hash-chain + idempotency re-claim blocked + stale-lease `start()` raises + `recovery_decision` = RECONCILE/safe_to_retry=False → PASS. 8 boundary còn lại (WHY timeout, scanner/verifier dies, during-patch, ledger/learning persistence) cần production wrapper của Golden A/B expose boundary — không fake.
- **T11**: isolated temp git repo (identity riêng, main checkout KHÔNG bị đụng) + EvidenceAuthority → **RED `PRODUCT_BLOCKED`**.

## Residue còn lại của Bước 0 (phiên sau)
- **0.8 auth**: inventory toàn bộ credential fallback (token→password, query→token, env→implicit file, dev fallback); scheduler chọn `SCP_AUTH_TOKEN_SECRET ?? SCP_AUTH_PASSWORD` (claim từ external plan — grep scp/ CHƯA tìm thấy code, chỉ thấy docs — phải verify tại nguồn); `SCP_SCHEDULER_ADMIN_TOKEN` riêng; 7 auth test (no token 401, session_id-only 401, invalid 401, 429, conflicting fail-closed, scheduler wrong token, ws explicit token).
- **0.9 kernel mutation authority**: inventory 21 mutating SQL trong `taskkernel.py` → map semantic operation → transaction primitive thống nhất → crash injection 4 điểm. (Chưa làm — chỉ inventory.)
- **0.10 semantic firewall learning path**: chứng minh/bổ sung `fast_learning_engine` qua `inspect_untrusted()` (chưa kiểm tra code trong phiên này).
- **0.11 JudgeCoreMixin J1–J5**: caller graph bước đầu: production `.judge()` callers = `scp/core/streaming_factcheck.py:218` + stub `scp_v14`; decision procedure J2–J5 chưa chạy.
- **0.12**: benchmark THẬT (measured, monotonic_ns, p50/p95, same work units) thay cho ESTIMATE.
- Bước 0 exit gate: chạy khi các mục trên xong.

## Phân loại đỏ hiện tại (đỏ đúng lý do)
| Test | Lớp |
|---|---|
| T07 missing-piece discovery | PRODUCT_BLOCKED (epistemic boundary chưa tồn tại) |
| T09B verified-fix commits | PRODUCT_BLOCKED (reality_test module + gold evidence policy) |
| T11 EvidenceAuthority | PRODUCT_BLOCKED (chưa có runtime evidence authority) |

## Bổ sung 2026-09-02 (residue 0.8–0.12, cùng phiên)

### 0.8 Auth residue — ĐÃ SỬA + claims đối chứng
- **P0 còn sống đã bị diệt**: `api_server.py:442` `os.environ.get("SCP_ADMIN_KEY", "admin")` — fallback "admin" vẫn tồn tại (verified live 2026-08-29 nhưng code chưa sửa). Đã fail-closed: unconfigured → 401 (khớp convention của `verify_admin` canonical), sai key → 401.
- **Claim scheduler của external plan = PHẢN CHỨNG**: không có server code nào chọn `SCP_AUTH_TOKEN_SECRET ?? SCP_AUTH_PASSWORD` — chỉ benchmark scripts (client-side) đọc env để gọi API (hợp lệ). Không sửa gì; claim được ghi là refuted-with-evidence.
- 5 contract tests mới: `tests/T03_capability/test_auth_fail_closed_contract.py` (unconfigured 401 / wrong 401 / exact accept / ws session_id-only → 1008 / ws explicit token accept). 429 rate-limit để cho runtime profile (timing-based).

### 0.9 Kernel mutation authority — INVENTORY (refactor primitive để sau)
21+ mutating SQL sites trong `taskkernel.py`, tất cả nằm trong documented kernel methods, pattern event-first-then-projection: create (106), transition (87+142), claim 2 nhánh (173-174, 205-206 + expire-fail 195), start (246), heartbeat (260), release/expire (279, 292), checkpoint (311), record_action_dispatched (344-346), enter_reconciling (385), reconcile_unknown (415-426), idempotency_claim/retry (456, 461), idempotency_complete (483), commit_verification_result (506). Chưa thấy writer NGOÀI các method này (cần verify tiếp 0.9-full). Việc còn lại: transaction primitive thống nhất + crash injection 4 điểm + projection-rebuild equivalence test.

### 0.10 Semantic firewall learning path — ĐÃ WIRE
`fast_learning_engine_parts/fastlearningengine.py` (canonical learning engine) TRƯỚC ĐÂY không gọi `inspect_untrusted` (verified by grep — firewall chỉ phủ `_ask_impl`, `knowledge_curation`, `top_systems_learning`). Đã wire: RSS headlines (external ingress duy nhất của engine) qua `inspect_untrusted` — injected → DROP + đếm `news_headlines_quarantined`, không thành questions/facts.

### 0.11 JudgeCoreMixin — J1 caller graph + DECISION RECORDED
J1: `.judge()` production callers = `scp/core/streaming_factcheck.py:218` (SSE stream) + stub `scp_v14.py:26` (ủy quyền RealityJudge). Không có caller nào của JudgeCoreMixin ngoài cụm judge (grep toàn scp/). **Decision: KEEP JudgeCoreMixin canonical** — phased judge (`judge_phases.py`) hiện shadow-only, chưa chứng minh parity; deprecate chỉ sau J2–J5 (semantic inventory → shadow parity trên corpus cố định → adversarial parity → switch). Không xóa trước khi replacement có C-level evidence.

### 0.12 Benchmark — ESTIMATE được tách khỏi MEASURED
Engine giờ giữ `cycle_times_ms` (window 100) → `stats()` expose `cycle_times_n / p50_cycle_ms / p95_cycle_ms` (MEASURED); route `/v104/learn/fast/benchmark` trả thêm `measured_parallel` (MEASURED) song song với phần ESTIMATE đã nhãn. Benchmark thật hai-workload (sequential vs parallel cùng work units) vẫn là việc còn lại.
