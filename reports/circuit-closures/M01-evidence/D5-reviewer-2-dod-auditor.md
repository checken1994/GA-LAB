# Audit M1 — Soát chuẩn đóng mạch (D0–D8) — Boot & Background

- Vai trò: auditor độc lập (ngoài chuỗi agent fix), chỉ thu bằng chứng, không kết luận chốt.
- Repo: `C:\Users\check\Downloads\scp`
- Thời điểm audit: 2026-09-10 (giờ máy)
- Chế độ: READ-ONLY (không sửa file, không commit, không build/up, không chạy pytest toàn suite).

## SHA pin / trạng thái repo quan sát được

| Mục | Quan sát |
|---|---|
| git HEAD | `6328d513f53daf2cba03bf2d56a0bb380735f609` |
| branch | `audit/runtime-guard-AUDIT-20260909` |
| commit đóng M1 | `6328d51 fix(M1): boot/background circuit completed` |
| SHA pin nêu trong tài liệu mimosa/expert-panel | `fe4bc8d26f268222943e7ae30aed87267b3a2443` (commit trước `6328d51`) |
| git status cho 8 file phạm vi M1 | trống (không có thay đổi chưa commit trong các file phạm vi) |

Ghi chú: `git show --stat 6328d51` liệt kê 10 file: `.env.example`, `Dockerfile`, `compose.yml`, `reports/expert-panel/A-mach1-boot-fixes.md`, `scp/api/background_jobs.py`, `scp/api_server.py`, `scp/api_server_parts/lifespan.py`, `scp/policy/retry_policy.py`, `scripts/run_scp_acceptance.py`, `tests/T01_boot/test_flow_01_boot_background_scp_standard.py`.

## Bảng Mục DoD — Trạng thái quan sát

| Mục DoD | Trạng thái quan sát | Bằng chứng (lệnh đã chạy + trích output) | Ghi chú |
|---|---|---|---|
| **D0** Khóa phạm vi (liệt kê file + SHA nền + owner) | Chưa có bằng chứng | `git show --stat 6328d51` liệt kê đúng 10 file commit (8 file phạm vi + `compose.yml` + `reports/expert-panel/A-mach1-boot-fixes.md`). HEAD = `6328d51`. Không tìm thấy file kê khai D0 riêng (danh sách file + SHA nền + owner). | `reports/expert-panel/A-mach1-boot-fixes.md` có dòng "Scope files: đúng danh sách owner cho phép", nhưng không nêu SHA nền tường minh. |
| **D1** Contract tests nghiêm ngặt (suite chính exit 0; output artifact; cấm mock golden path; cấm skip/xfail) | Chưa có bằng chứng (không chạy test) + quan sát dấu hiệu cần lưu ý | `tests\T01_boot`: 3 file, tổng 36 `def test_` (26 + 3 + 7). `Select-String skip|xfail` trong `tests\T01_boot`: chỉ có comment `FA-02: No skip/xfail` (dòng 6) và 1 chuỗi `ski...` trong string PowerShell ở `test_supervisor_child_env.py:31`, không có decorator skip/xfail thực. File test chính có `unittest.mock.patch` tại các dòng 236-244, 263-270. | Không có artifact output của suite chính (exit code 0) trong `reports/circuit-closures` (thư mục không tồn tại). Commit message ghi "pytest 38 passed ... PIPESTATUS=0" nhưng không lưu artifact trong closure dir. |
| **D2** Runtime proof (LISTENING ở SHA pin; /health & /ready 200; luồng thật HTTP/WS/CLI; trace hash-chain; service identity == SHA pin) | Chưa có bằng chứng tại thời điểm audit | `docker ps --format ...` → chỉ có header, không có container nào chạy. | Không có service đang LISTENING để quan sát ở thời điểm audit. Commit message nêu Docker `/health` 200 nhưng không có artifact runtime trong repo. |
| **D3** Adversarial (suite exit 0; ≥1 probe khai thác thật chứng minh fail-closed) | Chưa có bằng chứng (không chạy) + có file suite | Suite liên quan tìm thấy: `tests\T04_kernel\test_adversarial_kernel_flaws.py` (45 test), `tests\T04_kernel\test_gap13_adversarial_challenge.py` (17 test), `tests\T10_recovery\test_adversarial_chaos_matrix.py` (2 test), `tests\T10_recovery\test_kernel_chaos_recovery.py` (2 test), `tests\T03_capability\test_flow_09_threat_analysis_scp_standard.py` (23 test). | Không có artifact output adversarial exit 0 trong closure dir (không tồn tại). |
| **D4** Ratchet bảo mật (Mimosa: HIGH = 0; HIGH toàn dự án không tăng so mốc trước) | Không đạt về mặt bằng chứng (lần scan gần nhất inconclusive) | `.mimosa\finding-ledger\v1\events\batch-stop-20260909T185026173Z-12696-f63f5c177db7.json`: `runStatus: "inconclusive"`, `coverage.status: "partial"`, `scanning.scanned_files: 0`, `failed_files: 6` (đúng 6 file phạm vi M1), reason `scanner_failed: spawnSync ...node.exe ETIMEDOUT`, `finding_count: 0`, `observedFindingIds: []`, `verifiedFiles: []`. Report: `.mimosa\reports\task-review-...json` cùng nội dung (`run_status: inconclusive`, `evidence_boundary.runtime_verification: not_performed`). | Ledger có 0 finding nhưng KHÔNG phải kết quả scan hợp lệ (0 file được scan). Commit message ghi "Mimosa focus rescan: hardcoded-credential 8 -> 6" và "Mimosa L3 commit gate disabled by owner decision 2026-09-10" — không thấy artifact scan hợp lệ cho mốc HIGH=0 của phạm vi M1. |
| **D5** Kiểm chứng độc lập (reviewer ngoài chuỗi fix; cấm self-approve) | Chưa có bằng chứng độc lập kiểm chứng được | Commit message nêu "Agent B code verify: MACH1_FIX_APPROVED". `reports/expert-panel\` có các báo cáo `A-mach1-boot-fixes.md` (agent A - bên fix), `B-kernel-p1.md`, `C-anti-goodhart.md`, `S-suite-repair.md`. | Không có chữ ký reviewer / bản duyệt claim độc lập dạng artifact trong closure dir (không tồn tại). Claim "Agent B code verify" chỉ là dòng trong commit message. |
| **D6** Fail loudly (AST phạm vi: 0 khối `except...: pass` không log; suy thoái có field quan sát; đường lỗi log warning trở lên) | Không đạt (quan sát 6 khối silent) | Script AST (đã chạy qua `python <file tạm>`): phát hiện 6 khối `except: pass` body chỉ có `pass`/docstring, không log: `scp\api_server_parts\lifespan.py:394`, `scp\api\background_jobs.py:228`, `scp\api\background_jobs.py:236`, `scp\api\background_jobs.py:290`, `scp\api_server.py:85`, `scp\api_server.py:386`. Đã kiểm chứng bằng đọc code: các block tương ứng chỉ có `pass` (vd `lifespan.py:394` `except Exception: pass`; `api_server.py:386` `except ImportError: pass`). | Đếm: TOTAL silent except-pass blocks = 6 (tất cả nằm trong 6 file .py phạm vi; `.env.example`/`Dockerfile`/test không tính). |
| **D7** Wiring & tài liệu (0 TODO dangling phạm vi; WIRED/CLOSED tại module header; flow map + runbook cập nhật; missing pieces liệt kê) | Không đạt một phần / chưa có bằng chứng | (a) `Select-String 'TODO'` trên 8 file phạm vi → không có kết quả (0 TODO). (b) 15 dòng đầu mỗi module phạm vi: `lifespan.py` (bắt đầu bằng `# Auto-extracted from api_server.py`), `background_jobs.py` (docstring mô tả registry, DNA #23/#19), `retry_policy.py` (docstring "Step 3: Auto-retry policy..."), `api_server.py` (docstring composition root) — KHÔNG có dòng trạng thái `WIRED`/`CLOSED` ở header. (c) Tìm flow map/runbook: `Get-ChildItem -Include *flow*map*,*runbook*,...` → 0 file; `Select-String 'runbook'` trong toàn bộ *.md → 0 kết quả. | Không tìm thấy file flow map hay runbook nào trong repo. Không có file missing-pieces tường minh cho M1. |
| **D8** Closure record (`reports/circuit-closures/M01-closure.json` gồm sha_pin, hash evidence, checklist D1–D7, known gaps, falsification_status, chữ ký reviewer; commit closure cùng commit đóng mạch) | Không đạt | `Test-Path 'C:\Users\check\Downloads\scp\reports\circuit-closures'` → `False`. `Test-Path ...\M01-closure.json` → `False`. `git show --name-only 6328d51 | Select-String 'closure|circuit|reports'` → chỉ có `reports/expert-panel/A-mach1-boot-fixes.md`. Tìm toàn repo file/dir tên `closure|circuit-clos` (ngoài node_modules) → không có `reports/circuit-closures`. | Thư mục `reports/circuit-closures` không tồn tại; `M01-closure.json` không tồn tại. Commit `6328d51` đóng mạch nhưng không kèm closure record. |

## Cách chạy / đọc công cụ

- Mimosa:
  - Không có lệnh `mimosa` trong PATH (`Get-Command mimosa` → lỗi không tìm thấy).
  - Không có file tool tên `mimosa` trong `tools\`; `Select-String 'mimosa'` trong `tools\*.py` → chỉ khớp các file trong `.mimosa\*` và `reports/expert-panel/A-mach1-boot-fixes.md` (không có script chạy).
  - Nguồn sinh ledger ghi `"source": {"component": "zcode-hook", "operationId": "Stop"}` → mimosa được kích hoạt như một hook (Stop) của zcode, không phải CLI standalone trong repo.
  - Đọc ledger (read-only, đã chạy được): `Get-Content '.mimosa\finding-ledger\v1\events\batch-stop-20260909T185026173Z-12696-f63f5c177db7.json' -Raw`.
  - Không tự chạy scan nặng (theo yêu cầu, và scanner hiện đang lỗi ETIMEDOUT).

## Facts (chỉ sự kiện quan sát được)

1. Tồn tại commit `6328d51` ("fix(M1): boot/background circuit completed") ở HEAD, branch `audit/runtime-guard-AUDIT-20260909`.
2. `git status` cho 8 file phạm vi M1 trống (không có thay đổi chưa commit trong phạm vi).
3. Thư mục `reports\circuit-closures` KHÔNG tồn tại; file `M01-closure.json` KHÔNG tồn tại; không có file/dir nào tên `*closure*`/`*circuit-clos*` trong repo (ngoài node_modules).
4. `docker ps` trả về không có container nào đang chạy (chỉ header).
5. Script AST phát hiện 6 khối `except ...: pass` (body chỉ có `pass`/docstring, không log) trong các file phạm vi: `lifespan.py:394`, `background_jobs.py:228`, `background_jobs.py:236`, `background_jobs.py:290`, `api_server.py:85`, `api_server.py:386`. Tổng = 6.
6. `Select-String 'TODO'` trên 8 file phạm vi trả về 0 kết quả.
7. 15 dòng đầu của `lifespan.py`, `background_jobs.py`, `retry_policy.py`, `api_server.py` không chứa chuỗi trạng thái `WIRED`/`CLOSED`.
8. Không có file flow map hoặc runbook nào tìm thấy theo tên; chuỗi "runbook" không xuất hiện trong bất kỳ file `.md` nào của repo.
9. Ledger mimosa mới nhất (`batch-stop-20260909T185026173Z-...json`) có `runStatus: inconclusive`, `coverage.status: partial`, `scanned_files: 0`, `failed_files: 6`, mọi lý do là `scanner_failed: spawnSync C:\Program Files\nodejs\node.exe ETIMEDOUT`; `finding_count: 0`; `observedFindingIds: []`; `verifiedFiles: []`.
10. `tests\T01_boot` có 3 file .py với tổng 36 hàm `def test_` (26 + 3 + 7).
11. Các suite tên khớp `adversarial|chaos|threat|attack`: `T04_kernel\test_adversarial_kernel_flaws.py` (45), `T04_kernel\test_gap13_adversarial_challenge.py` (17), `T10_recovery\test_adversarial_chaos_matrix.py` (2), `T10_recovery\test_kernel_chaos_recovery.py` (2), `T03_capability\test_flow_09_threat_analysis_scp_standard.py` (23).
12. File `Dockerfile` có `ARG SCP_GIT_SHA=unknown` (dòng 40) và `ENV SCP_GIT_SHA=${SCP_GIT_SHA}` (dòng 41).
13. `.env.example` tồn tại.
14. Commit `6328d51` không tạo/chạm bất kỳ file trong `reports/` nào ngoài `reports/expert-panel/A-mach1-boot-fixes.md`.
15. `reports\expert-panel\A-mach1-boot-fixes.md` (LastWriteTime 9/10/2026 1:24 AM) mô tả 6 fix cho M1 và ghi "Branch: audit/runtime-guard-AUDIT-20260909, HEAD fe4bc8d (chưa commit — working tree)".
16. SHA pin `fe4bc8d26f268222943e7ae30aed87267b3a2443` xuất hiện trong ledger mimosa, history summary, và trong expert-panel; HEAD thực tế hiện tại là `6328d51`.
17. File test chính `test_flow_01_boot_background_scp_standard.py` chứa `from unittest.mock import patch` và nhiều `patch(...)` (dòng 236-244, 263-270); dòng 381 ghi chú "with real tests (no MagicMock/AsyncMock for any subsystem...)".
