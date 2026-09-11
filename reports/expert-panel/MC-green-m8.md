# MC-GREEN — M8 (Audit/Benchmark) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC-GREEN.
Pin: `c0f5f6f575cf06c7baba6978ac0a2cfce1fbbbd0` (commit docs M7; không product fix).

## Phạm vi (D0)

- `/v105/audit/{stats,findings}` (verify_admin, group audit=full) +
  `/v3/hands/benchmark/batch*` (_guard PC-token, group batch_benchmark=full).
- Scope: audit_routes.py, batch_benchmark_routes.py, audit_fetcher.py,
  fitness_engine.py, test_flow_08.

## Kết quả D1–D8

- D1: 25/25 passed exit 0 tại pin (2.56s).
- D2: build + recreate tại pin (SHA từ git rev-parse), commit == pin, readiness
  ready.
- D3: 9/9 probe :8008 — 2 negative (401/403); audit stats/findings 200;
  **batch runner chạy thật end-to-end**: create PAUSED → status → resume →
  QUEUED → COMPLETED (completed=1, failed=1 — question giả định fail đúng);
  adversarial SSRF: metadata IP + internal host → 400 fail-closed; unknown
  job → 404. Teardown xong.
- D6: PASS — 0 silent except:pass / 15 handler.
- D7: PASS_WITH_LIMITS — 0 TODO; thiếu header STATUS + runbook.
- D4/D5: PASS_WITH_LIMITS (seal @1f00d00; không reviewer riêng).

## Probe-harness note

- Lần đầu extract jobId bằng py (native Windows) không đọc được path MSYS
  `/tmp` → G4/G5 đánh URL rỗng (307/404). Chạy lại với grep extract → PASS.
  Không phải lỗi route: `/batch/` rỗng → 307 FastAPI default, hợp lệ.
