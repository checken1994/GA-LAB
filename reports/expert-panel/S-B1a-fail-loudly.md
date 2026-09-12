# S-B1a — Fail-loudly census + fix cho `scp/core/` và `scp/meta/`

- Agent: S-B1a (Track B1 fail-loudly, lô 1)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`
- Base commit: `c2cd676` (docs(TB) V-TB follow-up amendment)
- Ngày: 2026-09-12
- Scope: CHỈ `scp/core/` + `scp/meta/` (bao gồm thư mục con: `question_fetchers/`,
  `partition/`, `fast_learning_engine_parts/`, `why_engine_parts/`, `why_sources/`).
  KHÔNG đụng tests/, GA.md, circuit-closures, dashboard, mini-services, autofix/runtime/security/knowledge.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## 1. Census (baseline của lô)

Script: `scripts/diagnostics/census_silent_except.py` (AST-based, đã commit để tái lập;
các patch script tạm trong cùng thư mục cũng được commit như evidence).

Định nghĩa SILENT (machine-checkable): handler `except` mà body KHÔNG chứa
logger-call / `raise` / return-lỗi-tường-minh (dict có key `error`, tuple/status
chứa exception, lỗi ghi vào accumulator `errors` được trả caller) / comment
`# silent-by-design` + reason.

Kết quả trên toàn bộ 524 handler trong scope:

| Nhóm | Số lượng |
|---|---|
| OK (has log/raise/explicit error return) | 375 |
| INTENTIONAL (silent-by-design, ban đầu) | 0 |
| **SILENT (cần fix)** | **149** |

Hai điều chỉnh census trong quá trình làm (đều ghi rõ):
1. Thêm nhận diện "return lỗi tường minh" → 149 → **130 SILENT thật** (giảm false-positive,
   vd `real_question_fetcher.py` trả `(source, [], e)` về cho caller).
2. Sau khi fix, 3 block được đánh dấu INTENTIONAL có reason (xem mục 3).

## 2. Fix theo module (commit per module)

| Commit | Module | Blocks |
|---|---|---|
| `e2502ab` | `scp/core/request_run_ledger.py` | 9 |
| `eab3327` | `scp/core/agent_autofix_adapter.py` | 4 |
| `59b5b1e` | `scp/core/agent_orchestrator.py` | 5 |
| `8eeb742` | `scp/core/question_fetchers/` (4 file) + `real_question_fetcher.py` | 18 |
| `15e72f9` | `scp/core/phase0.py` | 5 |
| `a1647e4` | `scp/core/chat_memory_store.py` + `code_evolution_agent.py` | 10 |
| `dad75ec` | `scp/core/math_evaluator.py` + `partition/{shard,archive}.py` + `top_systems_learning.py` | 14 |
| `f6a0c16` | `anchor`, `antibody`, `call_session_hub`, `context_pruner`, `cross_verify`, `hypothesis_zone`, `conflict_resolver` | 24 |
| `71b560b` | 21 file core còn lại | 34 |
| `2807fc8` | 13 file `scp/meta/` | 26 |

Tổng: **149 block được xử lý trong 56 file** (không còn block nào bỏ lại — lô sau không còn dư cho scope này).

Phân bố xử lý:
- `logger.warning(..., exc_info=True)`: persistence/query failures, corrupt JSONL
  ledger lines, dropped messages, calibration/capability fail-open — các lỗi mà
  caller cần biết nhưng không đổi return contract.
- `logger.debug(...)` + `# silent-by-design: <lý do>`: best-effort observability,
  optional-import fallback, parse-probe với documented default, external-fetch
  best-effort, cleanup, expected-disconnect — giữ nguyên hành vi.
- Re-raise: 0 block — không gặp rollback/security/kernel path nuốt exception
  trong scope này (block `except BaseException` của `bounded_evolution` đã
  propagate qua queue, chỉ thêm debug; `policy_materializer` đã re-raise sau cleanup).
- Comment-only (`silent-by-design`): 3 block đã loud sẵn hoặc lỗi được ghi nhận
  tường minh qua cấu trúc khác: `data_partitioner.py:232` (traceback + sys.exit(1)),
  `dependency_resolver.py:76` (missing import ghi vào report),
  `why_sources/wikipedia.py:232` (failure registered qua `_wiki_register_failure`).

Không đổi behavior runtime nào: mọi `return`/`continue`/`pass` fallback giữ nguyên;
13 file chưa có logger được thêm `logger = logging.getLogger(__name__)` (import stdlib).

Lưu ý evidence: `scp/core/request_run_ledger.py` chứa 388 lone-CR (line ending
`\r\r\n` được commit sẵn từ trước). Patch cho file này bảo toàn nguyên byte
newline; không normalize (tránh diff ồn ào).

## 3. Census sau fix

```
TOTAL except handlers: 524
OK(has log/raise): 521
INTENTIONAL(silent-by-design): 3
SILENT(need fix): 0
```

## 4. Verify (pytest + py_compile)

Baseline (chạy 1 lần trước fix đầu, commit `c2cd676`):
`python -m pytest tests/T03_capability/ tests/T02_contract/ -q` → **3 failed / 860 passed, EXIT=1**.

| Lần chạy | Điểm | Kết quả |
|---|---|---|
| Sau request_run_ledger | `e2502ab` | 3 failed / 860 passed (= baseline) |
| Sau question_fetchers | `8eeb742` | 1 failed / 862 passed (≤ baseline; xem flaky note) |
| Sau cluster A+B core | `dad75ec` | 3 failed / 860 passed (= baseline) |
| Sau toàn bộ core | `71b560b` | 3 failed / 860 passed (= baseline) |
| Sau toàn bộ meta | `2807fc8` | 3 failed / 860 passed (= baseline, xác nhận 2 lần liên tiếp) |

`py_compile` PASS cho từng file sửa (tổng 56 file).

### Flaky note (evidence hygiene)
- `test_flow_08_audit_benchmark_scp_standard.py::test_audit_stats_requires_admin`
  và `::test_audit_findings_requires_admin` là **order-dependent flaky**: fail trong
  full-suite baseline lẫn một số run sau fix, nhưng PASS khi chạy riêng (đã xác nhận
  `2 passed in 2.06s`). Không thuộc scope S-B1a (audit/benchmark path), không được sửa trong lô này.
- Một run giữa chừng báo `4 failed / 859 passed` nhưng tên test không kịp bắt;
  2 run xác nhận sau đó đều về đúng bộ 3 baseline failed → fail extra đó là transient.
- `test_bridge_execute_missing_token_clean_policy_denial_no_recovery` fail ổn định
  ở baseline lẫn sau fix (pre-existing, không đổi trạng thái).

Kết luận gate: **fail KHÔNG tăng so baseline** (3 = 3). PASS_WITHIN_SCOPE của
T02+T03 tại commit `2807fc8`; không claim gì vượt phạm vi này.

## 5. Limitations / open questions (DNA #22, #23)

- Census chỉ quét `except` block trong `scp/core/` + `scp/meta/`; các silent-failure
  dạng khác (return-code bỏ qua, `contextlib.suppress`, subprocess stderr nuốt)
  CHƯA thuộc census này — `contextlib.suppress` trong `file_mutex` đã thấy ở
  lock-unlink path và được giữ nguyên (best-effort, có TTL).
- Việc thêm logging không tự chứng minh "hệ thống fail-loudly đầy đủ": log level
  `debug` cần handler/log-config phù hợp mới nhìn thấy trong production — chưa
  audit cấu hình logging toàn cục (ngoài scope).
- 2 test flaky order-dependent là một hiện trạng riêng cần track riêng.
- Không chạy được integration/end-to-end proof (cấp C/D theo reality-verifier) —
  bằng chứng ở đây là static + unit-test profile (cấp A/B).

## 6. Evidence files

- Census script: `scripts/diagnostics/census_silent_except.py`
- Patch scripts (tái lập từng commit): `scripts/diagnostics/patch_s_b1a_*.py`
- Baseline pytest log: session log `call_302ca58ec4004074b596fcf9-stdout.log`
  (3 failed / 860 passed, EXIT=1 tại `c2cd676`)
