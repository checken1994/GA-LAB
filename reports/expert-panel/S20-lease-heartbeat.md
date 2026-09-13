# S20 — Lease Renew Primitive + Ask Heartbeat (Long-LLM Availability)

Ngày: 2026-09-13 · Worker: S20 (bỏ dở do mất điện) + S20d (tiếp nối, audit-first)
Nhánh: `audit/runtime-guard-AUDIT-20260909` · Base: `e0696f5` · Commit: **`925592c`**

## 1. Bối cảnh và thiết kế (phần S20 kế thừa)

Runtime evidence (`bench_final_seed99.json` + GA.md B11): provider free-tier latency
30–260s (mean 85.6s) trong khi lease của `/ask` là TTL cố định 60s. Lease hết hạn
dưới worker CÒN SỐNG, watchdog dời task, và state-route fail-closed S19 vứt bỏ
answer thật đúng (2/10 ask trên seed 99).

Fix theo owner-directive latency plan: KHÔNG tăng TTL (chỉ làm chậm phát hiện
crash thật) — thay vào đó holder chủ động renew lease trong khi còn sống:

- **`kernel.renew_lease(task_id, lease_id, fencing_token, ttl_seconds=None)`**
  (`scp/task_kernel_parts/taskkernel.py`) — expiry-only renewal.
- **`AskKernelAdapter._lease_heartbeat`** (`scp/ask_kernel_adapter.py`) — renew mỗi
  TTL/3 trong suốt attempt, stop trong `finally`.
- **`SCP_ASK_LEASE_TTL_SECONDS`** (compose interpolation, default 60) — chỉ để
  chạy proof có kiểm soát, default bảo toàn.

## 2. S20d — Audit diff kế thừa (AUDIT-FIRST)

S20 chết giữa đường; working tree còn 4 file chưa commit. Verdict audit: **GIỮ
NGUYÊN, KHÔNG cần vá** — thiết kế đúng spec, đối chiếu evidence-first:

- `renew_lease` chỉ gia hạn khi: lease row tồn tại + đúng `task_id`, `released=0`,
  `expires_at > now` (không hồi sinh lease đã chết), `fencing_token` khớp lease
  row VÀ là token MỚI NHẤT của task, `tasks.active_lease_id` khớp, task state
  trong `{LEASED, RUNNING, WAITING_TOOL, VERIFYING}`, global kill + epoch khớp.
  Kẻ chiếm cũ bị chặn ở 4 lớp độc lập → False (không raise).
- Expiry-only: chỉ UPDATE bảng `leases` (heartbeat_at/expires_at, version+1 theo
  pattern OCC của `heartbeat()` có sẵn). KHÔNG đụng tasks row, KHÔNG append event,
  KHÔNG sửa transition table (verified: diff không chạm `ALLOWED_TRANSITIONS`).
  State set còn chặt hơn `heartbeat()` hiện có (loại CHECKPOINTED/UNKNOWN — an toàn hơn).
- Heartbeat: renew mỗi TTL/3 (floor 0.05s); `renew_lease` False → log warning +
  dừng (không raise); infra exception → log + dừng; stop event + `wait_for`
  5s + cancel trong `finally`. TTL parse: default 60, lỗi/≤0 → 60; kill switch
  `SCP_ASK_LEASE_HEARTBEAT=0|false|off|no`.
- Schema dependency kiểm chứng thật: bảng `leases` có đủ `version`,
  `global_kill_epoch`, `heartbeat_at`, `issued_at`; `_control()` tồn tại;
  `expire_leases()` thật sự emit event reason `heartbeat_expired` (control test
  (c) phụ thuộc điều này).

## 3. Test results (PIPESTATUS discipline, exit codes ghi riêng)

| Suite | Kết quả | Exit |
|---|---|---|
| `tests/T04_kernel/test_lease_heartbeat.py` | **23/23 passed** (a–e: renew đúng/sai token/zombie/released-expired/no-state-change; E2E heartbeat-ON TTL 2s provider 5.2s → COMPLETED; control heartbeat-OFF → `lifecycle_authority_lost` reproduces; no-leak; env parse) | 0 |
| `tests/T04_kernel/` | 240 passed, 23 skipped | 0 |
| `tests/T10_recovery/` | 9 passed | 0 |
| `tools/t00_meta_audit.py` | All integrity checks passed (0 new regressions) | 0 |

### T02 flow02 — RED pre-existing, KHÔNG do diff S20 (A/B evidence)

- Full flow02 trên máy này KHÔNG exit 0 — cả tại HEAD sạch lẫn với diff S20.
- A/B: `git worktree` sạch tại `e0696f5` (không có diff) + cùng `.env` →
  `test_ws_chat_fail_closed_when_no_answer_source_available` **FAIL y hệt**
  (precondition `provider chain == []` vi phạm: `.env` cấp key thật cho
  groq/cerebras/gemini/nvidia; `_disable_openrouter` chỉ tắt OpenRouter).
- `test_ws_chat_rate_limit_exceeded_closes_1008` stall: 25 judge cycles × call
  provider cloud thật (30–260s/call) — environmental latency, không phải treo code.
  WS chat KHÔNG đi qua `run_rag` (grep: chỉ `/ask` ở `api_server.py:523` gọi),
  nên heartbeat S20 không thể ảnh hưởng đường này.
- flow02 trừ đúng test stall: **32 passed, 1 failed (chính là fail_closed
  pre-existing trên), 1 deselected** — 10m03s.
- Xử lý: KHÔNG force xanh; không sửa file ngoài scope; ghi nhận làm giới hạn.

## 4. Runtime proof trong Docker (TTL=2s, container thật)

`docker compose build scp-api` exit 0 (image chứa diff S20) →
`SCP_ASK_LEASE_TTL_SECONDS=2 docker compose up -d scp-api` → /health 200 (~5s),
`printenv` xác nhận TTL=2 trong container. Mint token bằng `SCP_ADMIN_KEY` trong
container (không in secret). POST `/ask` câu đơn giản:

| Chỉ số | Giá trị |
|---|---|
| Elapsed (wall clock) | **207.5s** (elapsed_ms=75864 là provider time; phần còn lại là judge/pipeline) |
| Verdict | FAIL — `[SCP: Answer withheld — evidence not verified: judge_pass]` |
| Answer head (60 ký tự) | `[SCP: Answer withheld — evidence not verified: judge_pass]` |
| `lifecycle_authority_lost` | **KHÔNG** (AUTHORITY_LOST=False) |

Kernel-level evidence (sqlite read-only trong container, task `ask-bcf8bcc9e753b42377795705`):

- Lease **version=307** → heartbeat renew **~307 lần** (2s TTL → interval 0.67s
  × 207s ≈ 309 ticks — khớp).
- Lease sống **206.9s** trên TTL 2s (~100 TTL liên tiếp) — crash detection vẫn
  nguyên (process chết = ngừng renew).
- Events: `task_created, ask_lifecycle×3, lease_granted, lease_valid,
  checkpoint_written, ask_response_observed, ask_evidence_insufficient_or_contradicted`
  — **KHÔNG** `lease_expired`/`heartbeat_expired`, **KHÔNG** `lifecycle_authority_lost`.
- Final state `HUMAN_REVIEW` qua đường VERIFIER (judge từ chối chất lượng answer —
  đúng fail-closed chất lượng, same self-correction gap đã ghi ở B11), KHÔNG qua
  đường lease. Đáp ứng tiêu chí: có scp_answer thật, PASS/FAIL đều chấp nhận,
  miễn không chết vì lease.

Xong proof: `docker compose up -d scp-api` (unset TTL env) → TTL=60 default,
/health 200 sau ~10s. Container đã về trạng thái mặc định.

## 5. Commit

```
925592c feat(kernel): lease renew primitive + ask heartbeat (long-LLM availability) [S20 owner-directive latency plan]
4 files changed, 540 insertions(+), 1 deletion(-)
  scp/task_kernel_parts/taskkernel.py
  scp/ask_kernel_adapter.py
  tests/T04_kernel/test_lease_heartbeat.py
  compose.yml
```

File rác untracked (`bench_sha.txt`, `reports/SCP_FULL_RUNTIME_RAG_1000_RETRY_V3_2026-08-17.jsonl`)
để nguyên, không commit. Không commit/push GA.md (orchestrator tự làm).

## 6. Giới hạn bằng chứng (scope + reality)

- `PASS` chỉ có nghĩa: không quan sát thấy failure trong stated scope (23 test
  heartbeat + T04 + T10 + flow02-minus + 1 runtime proof đơn). Không claim
  production-ready tuyệt đối.
- Flow02 full KHÔNG exit 0 trên máy này — pre-existing tại HEAD `e0696f5` (A/B
  worktree), nguyên nhân môi trường (`.env` multi-provider + provider thật chậm),
  ngoài scope sửa của S20d. Cần session riêng (test-isolation cho provider chain
  hoặc fixture env) nếu orchestrator muốn xanh tuyệt đối.
- Runtime proof dùng 1 câu hỏi; elapsed 207.5s chủ yếu do judge/pipeline trên
  provider free-tier — không phải benchmark latency, chỉ proof lease availability.
- Rollback: `git revert 925592c` (không có migration schema — `renew_lease` dùng
  đúng bảng/cột hiện có).
- Commit local, CHƯA push (theo phạm vi nhiệm vụ S20d).

## 7. Skill DNA hashes (release-evidence discipline)

```
SHA256 (.agents/skills/scp-dna/SKILL.md):
4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10

SHA256 (.agents/skills/scp-task-kernel-review/SKILL.md):
f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334
```
