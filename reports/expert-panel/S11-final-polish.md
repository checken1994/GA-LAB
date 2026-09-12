# S11 — Final polish campaign (V6 concerns 1, 2, 6)

- Agent: S11 (polish cuối campaign — 3 việc nhỏ, commit per-việc)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`
- Base commit (đầu session): `236ae40` (chore(test): de-shape C-track tests — group 4)
- Ngày: 2026-09-12
- Task: V6 concern 2 (PlaywrightBackend.evaluate stub + hands_executor guard),
  V6 concern 6 (STATUS-LEDGER Track C3 row + CIRCUIT-FLOW-MAP rows), V6
  concern 1 (T00 known-red pin). KHÔNG đụng GA.md, mini-services/,
  my_fixes.patch, PROMPT_INJECTION_GAP_REPORT.md, .mimosa, .hypothesis.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-web-orchestration-safety/SKILL.md` | `2a4c98023709c441aa7720b8f3765083e8f5bec231899f952d8cb5d7134377a6` |

Cross-check: hash scp-dna khớp với hash ghi trong `C3-sandbox-evaluator.md`
(nguồn độc lập cùng thời điểm) → phương pháp hash nhất quán giữa các agent.

## Việc 1 — PlaywrightBackend.evaluate stub + hands_executor guard (V6 concern 2)

- Commit: `31d3dc1` — `fix(D1): PlaywrightBackend evaluate stub + hands_executor guard (V6 concern 2)`
- `scp/web_control/playwright_backend.py`: thêm method `evaluate(expression,
  target=None, **kwargs)` raise `NotImplementedError("PlaywrightBackend is
  read-only: evaluate() is not supported (anti-honeypot: no arbitrary JS
  execution). Use BrowserSession backend for CDP evaluate.")` trong section
  "BrowserSession-compatible surface (fail-closed for unsupported power)".
  Signature nhận `target` (positional/kwarg) để mirror
  `BrowserSession.evaluate(expression, target)` — call site hands_executor
  pass target positional nên phải nhận được, nếu không `TypeError` che mất
  NotImplementedError.
- `scp/hands/hands_executor.py`: thêm guard `HandsExecutor._browser_evaluate()`
  (sau `_browser_target`): `getattr(browser, "evaluate", None)` → không có/không
  callable → raise `NotImplementedError` fail-loud rõ ràng. 3 call site được
  đổi sang guard: `web.dom_snapshot` (2 lời gọi) + `web.wait_for_text` (1 lời
  gọi). Path default BrowserSession KHÔNG đổi: cùng lời gọi
  `browser.evaluate(expression, target)` như trước.
- Tests (`tests/T03_capability/test_playwright_backend.py`, +2):
  `test_backend_evaluate_fail_loud_anti_honeypot` (stub raise ở cả 3 call
  shape) + `test_hands_executor_evaluate_guard_fails_loud_without_evaluate`
  (guard fail-loud với browser surface không có evaluate).
- Verify: `python -m pytest tests/T03_capability/test_playwright_backend.py -q`
  → **31 passed** (29 cũ + 2 mới, 0 skip — chromium có trong env);
  `python -m py_compile` cả 2 file OK; regression M4
  `test_flow_04_control_hands_scp_standard.py` → **58 passed** (không đổi
  behavior). Ghi chú: 2 file product/test thuộc phạm vi M4 → theo regression
  clause, D2/D4 re-run của M4 vẫn là nợ owner (không mới — S12 đã chạm cùng
  file test từ trước).

## Việc 2 — STATUS-LEDGER Track C3 row + CIRCUIT-FLOW-MAP rows (V6 concern 6)

- Commit: `25ab5f0` — `docs(ledger): Track C3 row + C-flow map rows (V6 concern 6)`
- `reports/circuit-closures/STATUS-LEDGER.md`: thêm hàng Track C3 sau Track C2
  — pin `45a7dc8`, verdict `PASS_WITHIN_SCOPE`, closure record =
  `reports/expert-panel/C3-sandbox-evaluator.md` **ghi rõ đây là evidence
  report KHÔNG phải closure JSON chuẩn** (không tồn tại `C3-*-closure.json`),
  lý do: C3 là adoption track ngoài hợp đồng D0–D8; bằng chứng chính =
  `C3-sandbox-evaluator.md` + E2E `tests/T04_kernel/test_sandbox_evaluator_e2e.py`.
  Kèm cập nhật known-gap C2 ("flow-map chưa có hàng Track C2" → đã bổ sung).
- `reports/circuit-closures/CIRCUIT-FLOW-MAP.md`: thêm mục "Các track adoption
  ngoài 14 mạch (Track C1–C3, ADOPT-AND-FIX)" với 3 hàng C1 (pin `72da6d3…`,
  CLOSED_WITH_KNOWN_GAP), C2 (pin `5b4a6da…`, CLOSED_WITH_KNOWN_GAP), C3 (pin
  `45a7dc8`, PASS_WITHIN_SCOPE) — kèm cảnh báo không đọc thành CLOSED.

## Việc 3 — T00 known-red pin (V6 concern 1)

- Commit: `15d1654` — `docs(ledger): pin T00 known-red policy conflict (V6 concern 1)`
- `reports/circuit-closures/STATUS-LEDGER.md`: thêm mục "KNOWN-RED (policy
  conflict, chờ owner quyết)". Đã xác minh bằng chạy thật:
  `pytest tests/T00_integrity/test_meta_audit.py::test_meta_audit_no_skip_in_mandatory_tests`
  → **1 failed**. Nguyên nhân: 7 test file C1/C2/C3/D1 dùng `pytest.skip`
  declared-infra-skip (PG DSN `SCP_PG_TEST_DSN` / chromium không có) — đúng
  pattern declared-infra-skip nhưng xung đột T00 no-skip policy (AST scan chỉ
  miễn trừ `platform.system`). Danh sách 7 file đã scan AST xác minh. 2 câu
  hỏi chờ owner: (a) allowlist env-guard trong T00 gate, (b) giữ nguyên đỏ làm
  driver. KHÔNG sửa test, KHÔNG sửa gate.

## Reality check tóm tắt

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/T03_capability/test_playwright_backend.py -q` | 31 passed |
| `python -m pytest tests/T03_capability/test_flow_04_control_hands_scp_standard.py -q` | 58 passed |
| `python -m py_compile scp/web_control/playwright_backend.py scp/hands/hands_executor.py` | OK |
| `pytest tests/T00_integrity/test_meta_audit.py::test_meta_audit_no_skip_in_mandatory_tests -q` | 1 failed (known-red đã pin, chờ owner) |

## Remaining scope (không claim hoàn tất)

- T00 known-red là policy conflict chờ owner quyết (việc 3) — chưa xử lý.
- M4 D2/D4 re-run sau khi chạm file phạm vi M4 — nợ owner (pre-existing từ S12).
- S-commit này chỉ polish 3 concern V6; không đánh giá các mạch khác.

---

# TA2 — T00 declared infra-skip allowlist (policy A, owner-approved)

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Claim

T00 no-skip gate (`test_meta_audit_no_skip_in_mandatory_tests`) chuyển từ "chỉ
miễn trừ OS-conditional" sang policy A: chấp nhận **declared infra-skip** qua
allowlist tường minh `tests/T00_integrity/declared_infra_skips.json` — không nới
gate mù quáng, mọi case khác vẫn fail-closed.

## Gate logic trước/sau (`tests/T00_integrity/test_meta_audit.py`)

- **Trước (baseline `3f1690d`):** `test_meta_audit_no_skip_in_mandatory_tests`
  (hàm nguyên khối, ~dòng 41-93 cũ): AST scan mọi `T*/*py` trừ chính nó;
  `pytest.skip`/`importorskip` Call thật + không có chuỗi `platform.system`
  trong file → FAIL; `pytestmark` skip → FAIL vô điều kiện; decorator
  skip/xfail/skipif → FAIL trừ `platform.system`.
- **Sau:** gate được tách thành hàm testable `scan_mandatory_test_tree(tests_root,
  allowlist_path=None)` + loader fail-closed `_load_declared_infra_skip_allowlist`:
  - skip KHÔNG có entry allowlist → vẫn FAIL (message mới nêu policy A);
  - skip có entry nhưng reason không khớp `reason_patterns` của chính file đó → FAIL;
  - entry khai `env_guard_token` nhưng token không còn trong file source → FAIL;
  - entry stale (file bị xóa / không còn skip thật) → FAIL (contract phải reconcile);
  - allowlist thiếu/hỏng JSON/thiếu key (`file`, `reason_patterns`,
    `env_guard_token`, `justification`) / path tuyệt đối hoặc `..` / entry trùng → FAIL fail-closed;
  - `pytestmark` + decorator skip: **không bao giờ** được allowlist (giữ nguyên rule cũ);
  - skip hợp lệ → PASS và gate in `declared_infra_skips: 7 file(s), 14 pytest.skip
    call(s) ...` + từng file (green không im lặng), trả về records để pin test đối chiếu.

## Allowlist nội dung (7 entry, không wildcard)

| File | Track | reason_patterns | env_guard_token |
|---|---|---|---|
| `tests/T03_capability/test_playwright_backend.py` | D1 | `declared infra-skip` | `sync_playwright` |
| `tests/T04_kernel/test_pg_boot_runtime.py` | C1 | `declared infra-skip`, `INFRA-SKIP` | `SCP_PG_TEST_DSN` |
| `tests/T04_kernel/test_pg_event_bus.py` | C2 | `declared infra-skip`, `INFRA-SKIP` | `SCP_PG_TEST_DSN` |
| `tests/T04_kernel/test_pg_migration.py` | C1 | `declared infra-skip` | `SCP_PG_TEST_DSN` |
| `tests/T04_kernel/test_pg_storage_chaos.py` | C1 | `declared infra-skip`, `INFRA-SKIP` | `SCP_PG_TEST_DSN` |
| `tests/T04_kernel/test_pg_storage_parity.py` | C1 | `declared infra-skip`, `INFRA-SKIP` | `SCP_PG_TEST_DSN` |
| `tests/T04_kernel/test_sandbox_evaluator_e2e.py` | C3 | `declared infra-skip`, `INFRA-SKIP`, `psycopg unavailable` | `SCP_PG_TEST_DSN` |

Mỗi entry bắt buộc có `justification` non-empty; patterns khớp đúng reason thật
đã đọc trực tiếp từ từng file (không pattern thừa — ví dụ migration chỉ có 1
skip site nên không khai `INFRA-SKIP`).

## Contract tests (pin gate behavior, tmp_path, no-mock)

- `test_gate_accepts_declared_infra_skip_and_records_it` — skip trong allowlist
  → PASS + output ghi nhận.
- `test_gate_fails_on_skip_outside_allowlist` — skip lạ ngoài allowlist → FAIL.
- `test_gate_fails_on_undeclared_reason_inside_allowlisted_file` — reason không
  khai → FAIL.
- `test_gate_fails_when_env_guard_token_removed` — mất guard token → FAIL.
- `test_gate_fails_on_stale_allowlist_entry` — entry stale → FAIL.
- `test_gate_fails_closed_when_allowlist_missing` / `..._malformed_allowlist` /
  `..._entry_missing_required_keys` — contract hỏng → FAIL fail-closed.
- `test_declared_infra_skip_allowlist_pins_known_files` — pin 7 file + đúng
  số skip call (2/2/2/1/2/2/3 = 14); thêm/bớt entry phải sửa pin test một cách
  deliberate.

## Reality check

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/T00_integrity/test_meta_audit.py -q` (trước, baseline `3f1690d`) | 1 failed (`test_meta_audit_no_skip_in_mandatory_tests`) |
| `python -m pytest tests/T00_integrity/ -q` (sau) | 72 passed, exit 0 |
| `python -m pytest tests/T00_integrity/ tests/T04_kernel/ -q` (sau) | 277 passed, 23 skipped (toàn bộ declared infra-skip `SCP_PG_TEST_DSN not set ... declared infra-skip`), exit 0 |
| `pytest ... -rs` trên 7 file allowlist | mọi SKIP mang đúng reason khai báo; playwright không skip (chromium có sẵn trên máy này) |

## Remaining scope

- Known-red pin trong `reports/circuit-closures/STATUS-LEDGER.md` (mục
  KNOWN-RED) chưa được cập nhật ở session này — file thuộc vùng cấm sửa
  (circuit-closures, chỉ đọc); cần owner/handoff sau gỡ pin theo commit này.
- 23 skip chỉ chứng minh "không failure trong môi trường không có PG/chromium";
  không phải bằng chứng các path PG/browser chạy đúng — bằng chứng đó thuộc
  các run có `SCP_PG_TEST_DSN` + chromium (đã có trong closure records C1/C2/C3/D1).
- PASS = không thấy lỗi trong scope test T00+T04 local; không mở rộng thành
  claim release/production-ready.
