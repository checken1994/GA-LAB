# SCP Hardening — Cổng A/B/C/D/E/F/H theo Audit Blueprint — 2026-08-29

Triết lý chỉ đạo (theo yêu cầu chủ hệ thống): **tiến hóa dựa trên toán, không
cảm tính LLM** · **máy tự replay bằng chứng thay vì để người đọc** · **hard
gate cơ học trước và sau AI** · **bằng chứng không thể phản bác**.

## Cổng B/H — Continuous Fitness Engine (chống tiến hóa mù)

- `tests/golden/golden_dataset.json` — Golden Suite **đóng băng**: 100 quyết
  định (50 base × biến thể đúng/sai), seed `20260829`, sinh bởi
  `scripts/generate_golden_suite.py`, phủ 4 nhóm: math, conversion, logic,
  rag-grounding. Không mạng, không LLM chấm.
- `scp/core/fitness_engine.py` — SUT = **lớp xác minh deterministic**:
  `tier1_guard` (cấu trúc + grounding strict 1.0 cho RAG) + **solver tính
  lại** bài toán bằng AST-whitelist (Reality > Model: tính lại, đừng tin).
  Metrics: `decision_accuracy`, `false_accept_rate` (chỉ số nguy hiểm nhất),
  `avg_decision_ms`. Ledger: `data/fitness_history.jsonl` kèm
  `config_hash` của chính SUT.
- **Evolution Gate** `gate(prev, next)`: PROMOTE chỉ khi accuracy không giảm
  ∧ false_accept không tăng ∧ latency ≤ +20%. Còn lại → ROLLBACK. Toán học,
  không cảm tính.
- **Baseline thật (2026-08-29)**: `accuracy=1.0, false_accept=0.0,
  false_reject=0.0, avg=0.023ms/decision`. Quá trình đạt baseline cũng là
  bằng chứng: 2 bug semantic thật đã bị suite bắt (grounding áp nhầm scope;
  "Đại Tây Dương" lọt qua overlap 0.6) và được sửa trước khi đóng băng.

## Cổng D — Two-Tier Verification (LLM không còn là Single Point of Truth)

- `scp/security/tier1_guard.py` — **Tier-1 deterministic (~0.02ms)**:
  REJECT_EMPTY / OVERLENGTH / CONTROL_CHARS (zero-width, bidi) /
  INTERNAL_MARKER / GROUNDING. Chém ngay, không tốn một token LLM.
- `scp/runtime/judge.py` — Tier-1 chạy TRƯỚC; Tier-2 (LLM) chỉ chạy khi
  Tier-1 sạch.
- `scp/runtime/judge_llm.py` — **tri-state cascade**: PASS / FAIL /
  None. FAIL → second opinion qua provider mạnh hơn (`task="autofix"`);
  hai model BẤT ĐỒNG → `None` → judge trả `UNKNOWN + ESCALATE` cho người
  thay vì KILL oan. Model lỗi/mạng lỗi → ESCALATE (fail-closed đúng nghĩa:
  không ai bịa quyết định).

## Quorum WHY + Cross-Falsification (chống ảo giác đồng thuận)

- `scp/security/quorum_why.py` — action R2/R3 phải qua hội đồng 3 provider
  khác nhau: KHÔNG vote kết quả (WHAT) — mỗi model xuất trình **WHY**;
  WHY của A bị ném cho B/C **bẻ gãy**. 1 vết nứt duy nhất → HUMAN_REVIEW;
  thiếu 1 WHY / model lỗi / trả lời rỗng → HUMAN_REVIEW (fail-closed).
  R0/R1 bỏ qua (NOT_REQUIRED). Đây là điều kiện cần — điều kiện đủ là các
  hard gate cơ học (capability token, canary, lease, postcondition) đã có
  trong TaskKernel + capability_epoch.

## Cổng F/C — Event-Sourcing Crash Recovery (máy replay, người không đọc log)

- `TaskKernel.recover_on_boot()` — lúc boot: verify hash-chain của MỌI
  task → rebuild projection từ journal → task dở dang được đưa về trạng
  thái an toàn theo đúng `ALLOWED_TRANSITIONS` (RUNNING/VERIFYING→
  HUMAN_REVIEW; LEASED/WAITING_TOOL→RECOVERING; CHECKPOINTED→QUEUED).
  **Journal hỏng → KHÔNG tự sửa** (fail-closed với bằng chứng), chỉ báo cáo.
- `tests/test_kernel_chaos_recovery.py` — bằng chứng bằng **kill thật**:
  process con bị `TerminateProcess` khi task đang RUNNING → boot lại →
  recovery đúng → hash-chain còn nguyên. Kèm test giả mạo journal: hệ
  thống từ chối tự sửa.

## Cổng A — Hermetic Boot (chạy được trên mọi môi trường)

- `tests/reality-tests/reality_4-e-002.py` — boot server từ **môi trường
  trắng** (chỉ SYSTEMROOT+PATH+TEMP, env file riêng với 2 secret ngẫu
  nhiên, không đọc .env repo): `/health` 200 với contract identity xác
  định, `/ready` 200 (judge init không cần Ollama/network), boot log
  **0 vết 11434**.
- Finding thật khi viết test (được ghi trong docstring): probe boot phải
  log ra FILE — stdout PIPE đầy 64KB làm logging block event loop và treo
  toàn bộ server.

## Cổng E — Sandbox: trung thực trước, cứng sau

- `os_sandbox.isolation_capability()` — báo cáo khả năng isolation THẬT
  của môi trường (job_object / bwrap / rlimit_only_not_a_sandbox /
  subprocess_only_not_a_sandbox), expose tại `/health/detailed.sandbox_
  capability`. Không phóng đại — `rlimit` KHÔNG được gọi là sandbox.
- Roadmap (khai báo, không claim): bwrap/seccomp trên Linux và Firecracker
  MicroVM là công việc hạ tầng riêng, không thể "pass" bằng code Python
  trên máy Windows — mọi claim ngược lại sẽ là ảo giác.

## Wired Brain ( Reality Check v2 — 3 vết rách đã vá, có test khóa)

1. **Dirty refactor**: toàn bộ định danh `_ollama_*` / log "[CHATBOT]
   Ollama" đã được rename (`_generated_answer`, "[CHATBOT] LLM (...)").
   Public route paths (`/v104/learn/ollama`) giữ nguyên vì dashboard đang
   dùng — ghi rõ là contract legacy.
2. **Rate-limit cơ học**: `TokenBucket` (30 burst / refill 75s ≈ 48 req/h
   < 60 GitHub) chạy TRƯỚC mọi fetch — hết token → chờ bounded hoặc raise
   `local_rate_limit_timeout`; không còn "hy vọng" mạng tử tế.
3. **Wired brain**: `advise()` giờ được đọc bởi WHY Gate (mọi kernel
   transition quan trọng thấy tham chiếu `[TOP1%]`) và bởi `_build_fix_
   prompt` (LLM vá code nhận tham chiếu warehouse). Tests:
   `tests/test_knowledge_wiring.py`.

## Bằng chứng tổng (2026-08-29)

- pytest: **161 passed, 1 skipped** (31 tests mới cho hardening)
- reality suite: **76/76** (gồm `4-e-001` warehouse, `4-e-002` hermetic boot)
- pre_push_gate.ps1: PASS (từ commit trước — chạy lại khi release)
- Tất cả tests hardening chạy < 10s, không mạng (hermetic), trừ reality
  boot test tự kiểm soát mạng của chính nó.

## Giới hạn được khai báo trung thực (DNA #23)

- Decoupling api_server → dumb router + tách kernel thành process riêng qua
  message queue: là **kiến trúc mục tiêu**, chưa làm trong đợt này (blast
  radius lớn, cần batch riêng).
- Firecracker/bwrap: cần Linux/môi trường ảo hóa; trên Windows chỉ có Job
  Object — capability report là thật, không phải quảng cáo.
- Fitness Suite đo LỚP XÁC MINH deterministic; fitness của full pipeline
  LLM (độ chính xác ngữ nghĩa) cần chế độ "llm" ghi provenance — thiết kế
  sẵn trong engine, chưa bật mặc định vì chi phí + non-determinism.
