# EXPERT C — Test Architecture / Anti-Goodhart — Progress Log

- Branch: `main` (local commits only, KHÔNG push)
- Ngày: 2026-09-05
- Scope cho phép: `tools/verify_scp_target_test_coverage.py`, `tools/t00_meta_audit.py`,
  `tests/T00_integrity/test_meta_audit.py`, progress log này, + sửa PRODUCT tại điểm
  lỗi do hardening phát hiện (tăng chuẩn, không hạ chuẩn).
- Cấm đụng (tôn trọng): `scp/task_kernel*`, `scp/hands/task_kernel_bridge.py`,
  `tests/T04_kernel/` — không file nào trong commit này đụng vào.
- Repo note: unstaged changes của expert khác (`scp/autofix/engine.py`,
  `scp/autofix/runner_phases/ast_scan.py`) — KHÔNG được add vào commit của C.

## 0. Baseline (trước mutation, cùng working tree)

| Check | Kết quả |
|---|---|
| `python -m pytest tests/T00_integrity/ -q` | 57 passed |
| `python tools/verify_scp_target_test_coverage.py` | OK: capabilities=138 edges=67 claims=47 status_counts={'TEST_BOUND_CONTRACT': 6, 'TEST_BOUND_PARTIAL': 41, 'UNPROVEN': 158} |

Evidence ban đầu:

- Không có `pytestmark` nào trong `tests/` + `scp/tests/` → detector mới không tạo
  BASELINE_DEBT giả (đã xác nhận lại bằng lần chạy meta-audit thật: debt giữ nguyên 5 historical).
- Không có decorator skip/xfail/skipif thật trong `tests/T*` → thêm check decorator không vỡ gì.
- Real `pytest.skip()` call trong `tests/T*`: 3 chỗ —
  `test_pass_never_means_complete_scp.py:38` (điều kiện trạng thái, không OS-conditional)
  và `test_os_sandbox.py:10,22` (có `platform.system` → hợp lệ).
- 122 selector / 86 unique node trong `spec/scp_target_test_coverage.yaml`:
  85/86 pass hardened check; duy nhất
  `tests/T02_contract/test_god_split_semantic_parity.py::test_split_target_imports`
  (claim `world.source_registry`) có 0 assert / 0 pytest.raises.

## 1. Hole #1 — `_node_exists` existence-only → HARDENED

`tools/verify_scp_target_test_coverage.py`:

- `_body_asserts_verification` (mới): walk AST thân function; đếm `assert` statement
  hoặc call `pytest.raises(...)`; KHÔNG descend vào nested `def`/`class`/`lambda`
  (fail-closed: assert trong nested def chưa chắc chạy lúc runtime của test).
- `_is_executable_test_node` (mới): node cuối phải là function `test_*` (hoặc class
  chứa ≥1 method `test_*` đạt check body) VÀ có assertion tự thực thi.
- `_node_exists` (harden): giữ nguyên ngữ nghĩa intermediate-node-phải-là-class;
  node cuối bắt buộc qua `_is_executable_test_node` → `def test_x(): pass`,
  helper không `test_`, class rỗng test đều từ chối claim.

## 2. Hole #2 — module-level `pytestmark` vô hình → ĐÓNG ở CẢ HAI detector

- `tools/t00_meta_audit.py` (FA-01, delta-based): `AuditVisitor` thêm
  `visit_Assign`/`visit_AnnAssign`/`visit_AugAssign` — target Name `pytestmark`
  với value tham chiếu `pytest.mark.{skip,xfail,skipif}` (dạng Call hoặc bare
  Attribute, gồm cả list/tuple) → finding `pytestmark <mark> in <scope>`.
  Cập nhật dòng SCOPE print cho trung thực.
- `tests/T00_integrity/test_meta_audit.py` (quét tĩnh): helper
  `_pytestmark_skip_marks` + `_pytestmark_assignment` → quét tất cả `T[0-9][0-9]*`
  gate dirs; pytestmark skip là violation tuyệt đối (không có escape OS vì nó
  skip nguyên file).

## 3. Hole #3 — quét mandatory-skip 4/12 gates → 12/12

`tests/T00_integrity/test_meta_audit.py::test_meta_audit_no_skip_in_mandatory_tests`:

- `mandatory_dirs` = mọi `tests/T[0-9][0-9]*` (T00-T11, gồm cả T03_integrity phụ),
  có assert `len >= 12` chống việc dirs biến mất.
- Giữ nguyên luật shipped cho call-skip: real `pytest.skip/importorskip` phải
  OS-conditional (`platform.system` trong source).
- Thêm (strict hơn, không vỡ gì vì 0 usage hiện tại): decorator
  `pytest.mark.{skip,xfail,skipif}` cũng phải OS-conditional. Bug tự phát hiện
  qua negative control: `@pytest.mark.xfail` là chuỗi Attribute
  (pytest→mark→xfail) chứ không phải bare Name → đã sửa matcher receiver-agnostic
  theo đúng semantics FA-01 của `t00_meta_audit.py`.

## 4. Sửa PRODUCT tại điểm lỗi (tăng chuẩn)

1. `tests/T02_contract/test_god_split_semantic_parity.py::test_split_target_imports`
   — thêm `assert module is not None` sau `importlib.import_module`. Assertion là
   BỔ SUNG (cơ chế fail bằng import error giữ nguyên); giúp claim
   `world.source_registry` hợp lệ dưới hardened `_node_exists`. KHÔNG xóa claim.
2. `tests/T00_integrity/test_pass_never_means_complete_scp.py::test_green_suite_counts_can_never_satisfy_completion`
   — thay `pytest.skip(...)` điều-kiện-trạng-thái bằng assert CẢ HAI nhánh
   (completion_satisfied → claim phải khác FORBIDDEN; ngược lại → FORBIDDEN).
   Guard không còn biến mất âm thầm khi trạng thái flip; quét 12 gates giữ luật
   nghiêm không cần ngoại lệ. **Bonus root-cause:** bản gốc (commit local 6839310,
   chưa có trên origin/main) chứa FA-01 violation tiềm ẩn — đã chứng minh bằng
   `audit_content(head_version, "", path)` trả về 1 new violation; sửa này gỡ
   blocker đó cho `tools/t00_meta_audit.py`.

## 5. Test mới (trong tests/T00_integrity/test_meta_audit.py, +6)

- FA-01 pytestmark: new violation / historical debt / bare Attribute / mark thường
  (`pytest.mark.slow`) không flag / `get_fa01_signatures` trực tiếp.
- `_node_exists`: positive (assert, `pytest.raises`, class chứa test thật) và
  negative (pass-only, helper không `test_`, assert trong nested def, class rỗng test).

## 6. Negative controls (end-to-end, dùng đúng detector thật)

Probe file tạm trong `tests/T02_contract/` (đã xóa sạch sau probe):

| Probe | Kết quả quét T00 |
|---|---|
| `pytest.skip()` call trong test | BẮT ("contains a real pytest.skip() call") |
| chỉ `pytestmark = pytest.mark.skip(...)` | BẮT ("silently skips the entire file") |
| chỉ `@pytest.mark.xfail` | lọt lần 1 → fix Attribute-chain → BẮT |
| `@pytest.mark.skipif(...)` | BẮT |
| sau khi xóa probe | green lại |

## 7. Verification cuối

| Check | Kết quả |
|---|---|
| `python -m pytest tests/T00_integrity/ -q` | **63 passed** (57 cũ + 6 mới) |
| `+ tests/T02_contract/test_god_split_semantic_parity.py` | **94 passed** tổng |
| `python tools/verify_scp_target_test_coverage.py` | **OK**, exit 0 — 138 caps / 67 edges / 47 claims; KHÔNG claim nào newly-failing (86/86 node bind pass hardened check sau product repair) |
| `python tools/t00_meta_audit.py` (full, origin/main trusted base) | **EXIT 0 — 0 new regressions**; debt giữ nguyên 5 historical; FA-02 không mất nodeid |
| Ruff (5 file đổi) | 0 lỗi mới so với baseline (parity: verify=4, t00=15, test_meta_audit=10, T02=8; pass_never: I001/PLW1510 có sẵn từ HEAD) |
| `py_compile` 5 file | OK |

L4 CODEOWNERS warning khi chạy meta-audit là local warning (tests/, tools/t00 là
protected paths); governance thật là server-side ruleset — không phải blocker local.

## 8. Giới hạn bằng chứng (PASS ≠ COMPLETE)

- Meta-audit so với `origin/main` local ref (không fetch mạng); trusted_base hiện
  hành theo `spec/guardrail_policy.yaml`.
- Quét tĩnh T00 chỉ đọc top-level `*.py` của mỗi gate dir (đúng shape shipped);
  file lồng sâu hơn vẫn do lớp FA-01 delta phủ (rglob toàn tests/ + scp/).
- Escape hatch 'platform.system' của luật call/decorator là string-match shipped —
  về lý thuyết có thể qua mặt bằng quote chuỗi; lớp FA-01 delta + L4 human review
  là lớp phòng còn lại.
- `_body_asserts_verification` fail-closed với test gọi helper chứa assert —
  pattern đó sẽ bị từ chối và phải viết lại test có assert tường minh.
- PASS ở đây chỉ nghĩa: các check nêu trên chạy xanh trên working tree này, trong
  scope đã nêu; không claim release-ready hay production-ready.

## 9. Commit

- files: tools/verify_scp_target_test_coverage.py, tools/t00_meta_audit.py,
  tests/T00_integrity/test_meta_audit.py,
  tests/T00_integrity/test_pass_never_means_complete_scp.py,
  tests/T02_contract/test_god_split_semantic_parity.py,
  reports/expert-panel/C-anti-goodhart.md
- prefix: `fixC(t00):` — KHÔNG push.
