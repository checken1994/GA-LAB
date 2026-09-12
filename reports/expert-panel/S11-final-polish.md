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
