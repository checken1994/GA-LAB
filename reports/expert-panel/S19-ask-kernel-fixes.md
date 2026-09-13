# S19 — /ask kernel: finalize transitions (RECONCILING/HUMAN_REVIEW) + per-question logical-ask id

- **Worker:** S19
- **Date:** 2026-09-13
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (không đổi, theo chỉ đạo)
- **Trigger:** Benchmark live-LLM đầu tiên trong container Docker (2 provider family OpenRouter + NVIDIA) phơi 2 bug PRODUCT thật ở `/ask`.
- **Skills bound (mandatory):** `scp-dna`, `scp-task-kernel-review` (SHA256 ở cuối report)
- **Base commit (pre-fix):** `37d741924572b27bf265ec03e984f07e3ccf0666`

## 1. Problem statement

Bug 1 — HTTP 500 khi `finalize` transition vào `VERIFYING` trong lúc task đã
bị recovery machinery dời khỏi happy path. Stacktrace runtime từ container
(chứng cứ, khớp `scp/ask_kernel_adapter.py:397` và `taskkernel.py:424` của
base commit):

```
scp.task_kernel.InvalidTransition: RECONCILING->VERIFYING
```

Bug 2 — sau khi MỘT logical ask được tạo, các ask kế tiếp trả 200 nhưng
`verdict=FAIL`, `falsification_status=KERNEL_GATE`, message
`KernelError - stable logical ask already exists`, `elapsed_ms 0.0` — kể cả
câu hỏi CHƯA TỪNG hỏi ("What is 12*8?"). Endpoint chết hàng loạt sau câu đầu
tiên (seed 42 re-run + seed 7 timeout cùng họ này).

## 2. Why chain + root cause (file:line ở base commit)

### Bug 1

1. Tại sao 500? `AskKernelAdapter.finalize` (line 397) giả định task còn ở
   `RUNNING` và gọi `transition(VERIFYING)` vô điều kiện.
2. Tại sao task không còn RUNNING? `begin()` cấp lease TTL 60s
   (ask_kernel_adapter.py:171). Với provider degradation (W2 đo 30–180s/ask),
   lease hết hạn giữa chừng handler; `expire_leases` / `auto_reconcile_orphans`
   (taskkernel.py:703-733, :1451+) sweep RUNNING→RECOVERING→RECONCILING vì
   `recovery_decision('LOST_RESPONSE', action_dispatched=True)` → RECONCILING
   (taskkernel.py:1710-1718). Response tới sau đó → RECONCILING→VERIFYING
   không có trong `ALLOWED_TRANSITIONS` (task_kernel.py) → raise.
3. Cùng family (W2 witness bug #1, `ask_kernel_adapter.py:411` trên SHA của
   W2 — tương ứng khối `else:` transition→HUMAN_REVIEW, line 421-427 ở base):
   task ĐÃ ở HUMAN_REVIEW (boot recovery RUNNING/VERIFYING→HUMAN_REVIEW,
   taskkernel.py:1605-1607; hoặc lease-expiry sweep VERIFYING→HUMAN_REVIEW,
   taskkernel.py:716-718) khi finalize escalate lần hai →
   `InvalidTransition: HUMAN_REVIEW->HUMAN_REVIEW` → cũng 500.

### Bug 2

1. Tại sao câu mới cũng collide? `_task_id` (line 121):
   `identity = request_id or f"{session_id or ''}|{input_hash}"`.
   Khi client gửi idempotency key, key THAY THẾ toàn bộ hash của
   question+evidence — mọi câu hỏi khác nhau mang cùng một key (client/replay
   dùng key per-run) đều map về task của CÂU ĐẦU TIÊN.
2. Tại sao thành cái chết hàng loạt? `create_task` va PRIMARY KEY → branch
   IntegrityError (line 213-234) định tuyến qua `_duplicate_is_reaskable`:
   duplicate ĐANG in-flight (RUNNING/RECOVERING/RECONCILING — do chính bug 1
   bỏ lại zombie in-flight) KHÔNG reaskable → raise
   `KernelError("stable logical ask already exists")` (line 234) →
   `run_rag` bắt thành `_kernel_blocked_response` → KERNEL_GATE, elapsed 0.
2. Hai bug khuếch đại nhau: bug 1 để lại task in-flight vĩnh viễn; bug 2 biến
   task zombie đó thành mutex chặn cả endpoint.

Missing piece đã đóng: không còn suy đoán — cả hai repro đúng từng dòng ở
mục 5 (runtime trong container).

## 3. Quyết định thiết kế BUG 1: (b) finalize route theo state hiện tại

Không chọn (a) thêm `RECONCILING→VERIFYING` vào transition table. Lý do:

- `enter_reconciling`/`auto_reconcile_orphans` cố ý **release lease** và xóa
  `active_lease_id` (fencing). Kể cả khi thêm edge, `transition("VERIFYING")`
  vẫn chết ở Lease Authority Gate (taskkernel.py:447-469,
  `StaleLease: ... requires active lease authority`) — muốn đi tiếp phải bypass
  luôn fencing: đúng cái anti-pattern mà `scp-task-kernel-review` cấm
  ("Worker cũ commit → bị từ chối STALE_LEASE").
- Hợp đồng recovery tự nó ghi rõ: `reconcile_unknown` — *"reconcile an
  uncertain side effect **without auto-completing** the task"*;
  `recovery_decision` RECONCILE → escalation `'human_review_if_unknown'`.
  RECONCILING exit bằng luật tới `HUMAN_REVIEW`, không tới VERIFYING. Cho
  stale attempt đường tự hoàn thành là nới lỏng fail-closed.
- Bảng 17 state giữ nguyên → T10 recovery matrix không đổi ngữ nghĩa; không
  có edge mới nào lọt qua test matrix.

Routing trong `finalize` (sau sửa):

| State hiện tại lúc finalize | Hành vi |
|---|---|
| `COMPLETED/FAILED/CANCELLED` | giữ nguyên `_terminal_result` (withheld, như cũ) |
| `RUNNING` | transition→`VERIFYING` như cũ (happy path) |
| `VERIFYING` | tiếp tục verify (idempotent cho finalize retry) |
| `RECOVERING/RECONCILING/UNKNOWN/HUMAN_REVIEW` + mọi state non-intact khác | **không** gọi verify; trả `verification=INSUFFICIENT` (`lifecycle_authority_lost:<state>`), escalate qua edge hợp lệ → `HUMAN_REVIEW`, trace ghi nhận response ĐÃ được quan sát, HTTP 200 fail-closed với withheld answer |
| VERIFIED nhưng commit race (lease hết giữa slow judge — W2 họ này) | bắt `KernelError` quanh `commit_verification_result` → cùng đường intercept (`commit_raced_lease_or_state`) |

Tự-transition `HUMAN_REVIEW→HUMAN_REVIEW`: helper `_escalate_to_human_review`
mới — đã ở HUMAN_REVIEW thì **no-op + info log**; race state (InvalidTransition
/ StaleLease / OptimisticLockError đều là `KernelError`) thì **skip + warning**,
KHÔNG BAO GIỜ raise. Terminal state cũng trả về hiện trạng, không crash.

## 4. Fix BUG 2 tại điểm sinh id

`task_id_for(question, contexts, retrieved_context, session_id, request_id)`:

```python
input_hash = canonical_input_hash(question, contexts, retrieved_context)
scope = request_id or session_id or ""
return "ask-" + sha256(f"{scope}|{input_hash}")[:24]
```

Hash canonical của question+evidence **luôn** là discriminator per-question;
key/session chỉ còn là discriminator về *phạm vi retry* — đúng nghiệp vụ
idempotency: chặn ĐÔI LẠI cùng một câu hỏi (transport retry), không chặn mọi
câu hỏi khác. Không đổi semantics đã chủ đích:

- Cùng key + cùng body đang in-flight → vẫn dedupe fail-closed
  (`stable logical ask already exists`) — chứng minh bằng test đơn vị; giữ
  nguyên luật "một retry không dispatch handler hai lần".
- Cùng câu hỏi nhưng bản cũ đã **qua quyết định** (terminal/HUMAN_REVIEW) →
  re-ask uniquified như hợp đồng 2026-08-29 (không cached-result path vì
  kernel lưu lifecycle, không lưu final answer; ghi ở open questions).
- Key/session hash giờ khác id cũ → các zombie RECONCILING cũ của benchmark
  era không còn chặn request mới.

Harness mirror `scripts/run_scp_acceptance.py::stable_task_id` trước đây
 reimplement private formula (chính là cách harness drift khỏi product) → đổi
 thành import `AskKernelAdapter.task_id_for` (single source of truth). mọi
 assertion giữ nguyên độ nghiêm (vẫn tra đúng task id, vẫn verify journal).

## 5. Tests mới + kết quả

File mới `tests/T04_kernel/test_ask_kernel_lifecycle_and_identity.py` — 12 pass:

Bug 1: (1) `test_finalize_from_reconciling_returns_withheld_result_not_500`;
(2) `test_finalize_from_human_review_never_raises`; (3)
`test_double_escalation_is_idempotent_noop_not_raise` (mô phỏng đúng W2: race
sweep VERIFYING→HUMAN_REVIEW giữa lúc verify chậm — code cũ raise
`HUMAN_REVIEW->HUMAN_REVIEW`); (4)
`test_verified_commit_racing_stale_lease_does_not_500`; (5)
`test_normal_running_finalize_path_is_unchanged` (anti-placebo: happy path vẫn
ký receipt + commit COMPLETED, answer thật xuyên qua); (6)
`test_transition_table_stays_strict_reconciling_and_human_review` (pin thiết kế
(b): RECONCILING↛VERIFYING, HUMAN_REVIEW không self-edge, 3 recovery states
vẫn có edge→HUMAN_REVIEW).

Bug 2: (7) `test_task_id_for_always_includes_question_hash`; (8)
`test_same_key_different_questions_do_not_collide` (in-flight cùng key — đúng
kịch bản benchmark); (9)
`test_same_key_same_question_transport_retry_still_deduped`; (10)
`test_same_session_same_question_still_deduped`; (11)
`test_different_questions_same_session_both_run`; (12)
`test_reask_after_decision_runs_fresh_uniquified_task` (seed re-run behavior).

Regression bắt buộc (exit 0, `${PIPESTATUS[0]}`):

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/T04_kernel/ -q` | **217 passed, 23 skipped** (skip = PG variants, baseline) |
| `python -m pytest tests/T03_capability/ -q` | **782 passed, 2 skipped** |
| `python -m pytest tests/T10_recovery/ -q` (recovery matrix) | **9 passed** |
| `python -m pytest tests/T02_contract/test_flow_02_ask_chat_scp_standard.py tests/test_subsystem_task_kernel.py tests/T02_contract/test_god_split_semantic_parity.py -q` | 65 passed, 1 failed |

Failure duy nhất `test_ws_chat_fail_closed_when_no_answer_source_available`
**pre-existing**: đã `git stash -u` về đúng base tree và chạy lại — fail y hệt
(2.22s, cùng assert điều-kiện-độc-lập `llm_gateway._provider_chain("chat")`
rỗng trong khi env máy local có provider bật). `llm_gateway/` là scope S18 đã
đóng, không đụng tới. Không sửa test để cho xanh.

## 6. Runtime proof trong container (image rebuild từ code sửa, scp-api)

`docker compose build scp-api` exit 0 → `up -d` → `/health 200` sau ~3s,
`/readiness` `judge: ok`. Token mint bằng
`docker exec scp-scp-api-1 python -c "from scp.security.jwt_guard import
create_access_token; ..."` — giá trị token KHÔNG in ra log/report.

| # | Payload | Kết quả |
|---|---|---|
| A | `{"question":"What is 12*8?","session_id":"s19-runtime"}` (chính câu bị chặn 13/09) | HTTP 200, elapsed 199s — provider chậm → watchdog dời task sang RECOVERING giữa chừng; finalize mới intercept: `lifecycle_authority_lost:RECOVERING`, withheld, **không 500, không KERNEL_GATE**. Code cũ: crash đúng stacktrace bug 1 |
| B | `{"question":"What is the capital city of Japan?","session_id":"s19-runtime"}` | **verdict PASS**, confidence 0.85, governance UPHOLD, run_status SUCCESS, 28.6s, answer THẬT: "Thủ đô của Nhật Bản là Tokyo." — hết bị chặn sau câu đầu (bug 2 chết) |
| A repeat | cùng question A, cùng session | task cũ đã DECIDED (HUMAN_REVIEW) → re-ask hợp lệ, chạy fresh; lại chậm (188s) → intercept `lifecycle_authority_lost:RECONCILING` — **đúng state trong stacktrace gốc, giờ trả 200 fail-closed** |
| C (proof bug 2) | 2 câu KHÁC nhau (`999*7`, `capital of France`) **cùng header `X-SCP-Idempotency-Key: s19-shared-run-key`**, câu 1 còn in-flight | Câu 2 CHẠY THẬT 76s (code cũ: `elapsed_ms 0.0`, `falsification_status KERNEL_GATE`, "stable logical ask already exists") → interception `RECONCILING`. Dedupe per-key+per-question còn nguyên (unit test 9) |
| D | same key + same question (task cũ đã decided) | re-ask fresh — hành vi theo thiết kế |

Kernel DB (`task_kernel.sqlite3`, read-only): các task mới đều kết thúc
`COMPLETED` hoặc `HUMAN_REVIEW` — **không còn zombie in-flight do finalize
crash**; duy nhất 1 task `RECONCILING` còn lại từ 06:26Z (pre-fix benchmark
era) — nằm lại chờ reconcile/human theo đúng hợp đồng recovery.

## 7. Gates

- `python tools/t00_meta_audit.py` exit 0 — "0 new regressions".
- `python tools/verify_scp_test_skill_contract.py` exit 0 —
  `PASS_WITHIN_SCOPE` (SHA `scp-task-kernel-review` trong output khớp mục 9).
- Không đụng `GA.md`, `spec/`, `llm_gateway/`, `mini-services/`.

## 8. Evidence limits (G19/G22 — PASS ≠ TRUE)

- Proof trong giới hạn: 1 máy, 1 container uvicorn, loopback, provider thật
  qua quota 429-có-thể; latency math-ask ~190s → chưa chứng minh được answer
  THẬT cho câu số học dưới lease 60s hiện hữu (kiến trúc heartbeat long
  dispatch là việc khác, nằm ngoài phạm vi 2 bug này).
- Dedupe in-flight cùng key+question: chứng minh bằng unit test + DB state,
  chưa bắt kịp cửa sổ in-flight trong curl live (task đã decided khi curl D chạy).
- Pre-existing failure T02 chat fail-closed đã verify trên base tree nhưng chỉ
  trên máy này (env-dependent) — chưa loại trừ nguyên nhân môi trường khác.
- Không claim: endpoint an toàn/production-ready; chỉ: 2 bug cụ thể đã sửa tại
  điểm lỗi với bằng chứng unit + container runtime ở scope đã nêu.

## 9. SKILL binding hashes (mandatory)

SHA256 của 2 file skill đã đọc và áp dụng:

```
4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10  .agents/skills/scp-dna/SKILL.md
f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334  .agents/skills/scp-task-kernel-review/SKILL.md
```
