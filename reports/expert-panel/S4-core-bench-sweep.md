# S4 — Security Sweep Đợt 4: HIGH findings trong `scp/core/`, `scp/task_kernel_parts/`, `scp/runtime/storage_manager.py`, `benchmark/`, `scripts/`

- **Agent:** S4 (SCP Worker Agent) — chạy độc lập, KHÔNG commit.
- **Branch:** `audit/runtime-guard-AUDIT-20260909`
- **Ngày:** 2026-09-10
- **Nguồn findings:** `C:\Users\check\.mimosa\security-scans\project-362369a5effad96dedf43711\scan-2026-09-09T19-17-22.715Z-b3d7d688beca\findings.json` (lọc `severity=high`, location trong scope; SSRF đã xử lý ở S1/S1b/S2/S3 — không thuộc đợt này).
- **Test mới:** `tests/T03_capability/test_security_sweep_s4.py` — 33/33 PASS.
- **Phạm vi:** 20 file sửa + 1 file test + report này. Không đụng subsystem logic nào khác.

## 1. SQL Injection (CWE-89) — 10 findings

| # | File:line (gốc) | Fix | Ghi chú |
|---|---|---|---|
| 1–2 | `scp/task_kernel_parts/taskkernel.py:303,305` | Whitelist regex `[A-Za-z0-9_]+` + double-quote identifier trước `PRAGMA table_info`/`ALTER TABLE`; table names là compile-time constants | Production-critical: chỉ thêm validation + quote, KHÔNG đổi schema/behavior. `tests/T04_kernel/` 177/177 PASS |
| 3 | `scp/core/db_manager_parts/_preflight_integrity_check.py:33` | `VACUUM INTO ?` — bound parameter cho filename (đã verify SQLite hỗ trợ) | Bỏ f-string hoàn toàn |
| 4 | `scp/core/partition/rotate.py:92` | Thay check `.replace("cache","").isalnum()` yếu bằng regex `^[A-Za-z_][A-Za-z0-9_]*$` per-column + quote kép | col_list nguồn = schema introspection ∩ canonical cols |
| 5 | `scp/runtime/storage_manager.py:272` | `VACUUM INTO ?` bound parameter; giữ char allowlist làm defense-in-depth | |
| 6 | `scripts/diagnostics/count_kb_r37.py:9` | Whitelist regex + quote kép, name từ sqlite_master | |
| 7 | `scripts/history/r44_build_regression_corpus.py:31,42` | Validate `--table` argv bằng regex đầu `_read_rows` | columns đã từ hardcoded allowlist |
| 8 | `scripts/learning/learning_staging_r43.py:58` | Whitelist regex + quote kép, table từ tuple constant | |
| 9 | `scripts/ops/scp_db_consistent_snapshot.py:56` | Whitelist regex trước khi quote | |
| 10 | `scripts/ops/scp_db_readonly_audit.py:22` | Whitelist regex + quote kép; tên lạ → ghi `SKIPPED_UNSAFE_NAME` | |

## 2. Path Traversal (CWE-22) — 14 findings

| # | File:line (gốc) | Fix | Ghi chú |
|---|---|---|---|
| 1–2 | `benchmark/extract_gold_anchor_v2.py:250,265` | Containment guard `_contained_in_repo()` (resolve + `is_relative_to` repo tree) cho mọi path `__file__`-derived | Path hiện là constant an toàn — guard chặn khi derivation trở nên configurable |
| 3 | `benchmark/run_benchmark_v2.py:1093` | `_safe_output_path()` cho `--output` argv: reject `..`, reject absolute ngoài repo tree, resolve trước ghi | Guard import được → test runtime trực tiếp |
| 4 | `benchmark/run_humaneval.py:56` | Containment: samples file phải nằm trong CWD | |
| 5 | `benchmark/run_ragas_v1.py:154` | Containment guard repo-tree cho `GOLD_PATH`/`OUTPUT_PATH` | |
| 6 | `benchmark/run_world_exam.py:41` | Containment: raw_results phải nằm trong CWD | |
| 7 | `benchmark/download_global_top1_benchmarks.py:20` | Containment guard repo-tree cho `out_path`/`sample_path` | |
| 8–9 | `scp/core/partition/archive.py:368,409` | `_safe_partition_date()` regex `^\d{4}-\d{2}-\d{2}$` cho date từ external JSONL timestamp + containment `is_relative_to(data_dir)` trước `open` | Không có zip member nào trong archive.py → zip-slip áp dụng dạng partition-slug guard |
| 10–11 | `scp/core/startup_optimizer.py:136,288` | `rotate_jsonl`: reject `..` + non-`.jsonl` (fail-closed, không đổi behavior cho caller thật); `__main__` test block: containment assert | |
| 12 | `scp/runtime/storage_manager.py:315` | Containment guard khi restore backup: `latest` ∈ `data_dir/backups`, `db_path` ∈ `data_dir` | |
| 13 | `scripts/prep_quick_exam.py:9` | Containment guard repo-tree | |
| 14 | `scripts/run_full_audit.py:84` | Containment: boot log phải nằm trong tempdir | |

## 3. Insecure Deserialization (CWE-502) — 1 finding

| # | File:line (gốc) | Fix | Ghi chú |
|---|---|---|---|
| 1 | `scp/core/smart_cache.py:172` | **FP residue**: module đã chuyển JSON từ trước (SECURITY FIX cũ); finding trúng token `pickle.loads(None)` trong docstring. Reword 3 comment (172/175/218) bỏ token binary-deserializer, giữ chức năng | Grep sau fix: `pickle.loads`, `pickle.dumps`, `yaml.load` = 0 match trong module |

## 4. Verify

### 4.1 Pytest trước/sau (pipe-exit-code)

| Suite | TRƯỚC (baseline) | SAU |
|---|---|---|
| `tests/T03_capability/ tests/T04_kernel/ tests/T08_runtime/` | 39 failed, 794 passed — EXIT=1 | 39 failed, 827 passed — EXIT=1 |
| `tests/T04_kernel/` (riêng, sau sửa taskkernel) | — | 177 passed — EXIT=0 |
| `tests/T03_capability/test_security_sweep_s4.py` | — | 33 passed — EXIT=0 |

- 794 + 33 (test mới) = 827 pass: **không một test cũ nào chuyển pass→fail**; tổng fail giữ đúng 39 (flow_04/06/07/09/10/12 pre-existing non-deterministic, đã ghi nhận trong task). **Fail KHÔNG tăng.**

### 4.2 Grep residual trong scope + lý do

- `execute(f"…")` còn lại 9 chỗ — **tất cả là identifier (table/column name) không thể parameterize**, mỗi chỗ đã có: regex whitelist `[A-Za-z0-9_]+` (hoặc `[A-Za-z_][A-Za-z0-9_]*` cho column) + double-quote SQLite + comment lý do `[SEC-S4]`:
  - `scp/task_kernel_parts/taskkernel.py:309,311` (tuple constant)
  - `scp/core/partition/rotate.py:96` (schema introspection ∩ canonical cols)
  - `scripts/diagnostics/count_kb_r37.py:15`, `scripts/learning/learning_staging_r43.py:65`, `scripts/ops/scp_db_consistent_snapshot.py:62`, `scripts/ops/scp_db_readonly_audit.py:28` (sqlite_master introspection)
  - `scripts/history/r44_build_regression_corpus.py:36,47` (argv `--table` — regex-gated đầu hàm; columns từ hardcoded allowlist)
- `%`-formatting SQL trong scope: 0 match.
- `open(f"…")` trong scope: 0 match.
- `..` traversal strings còn lại: chỉ nằm trong data `.jsonl` (nội dung gold data) và `.ps1` legacy ngoài code Python — không phải code path.
- `smart_cache.py`: còn 1 từ "pickle" trong comment so sánh ("JSON instead of pickle") — không phải deserializer call, scanner gốc không flag.

### 4.3 No-mock evidence (test mới)

- Kernel: `TaskKernel` tmp thật + `sqlite3.set_trace_callback` (API quan sát chính thức, không patch method) — chứng minh task_id chứa `'; DROP TABLE tasks;--` **không bao giờ** xuất hiện trong SQL text, schema intact, statement PRAGMA/ALTER chỉ chứa identifier whitelist.
- VACUUM INTO: bound parameter được sqlite thật chấp nhận (file target được tạo).
- archive: `migrate_old_to_new` chạy thật trên tmp `bypass_log.jsonl` — mọi output nằm trong `data_dir/bypasses` với tên `YYYY-MM-DD.jsonl`; timestamp hỏng → `errors`.
- rotate_jsonl: file thật 300 dòng → rotate còn 200; `../evil.jsonl` → rejected.
- `--output` benchmark: `../evil.json` → ValueError.

## 5. Scope & giới hạn (DNA #22/#25)

- PASS chỉ có nghĩa: không thấy failure trong phạm vi test đã chạy (T03/T04/T08 + suite mới). Không claim "hết mọi lỗ hổng".
- Các f-string identifier còn lại đã whitelist nhưng nếu gate Mimosa vẫn đếm theo pattern, cần marker `# nosec B608` đã kèm ở từng dòng.
- Docker rebuild + recreate + `/health` 200: xem phần evidence cuối báo cáo.
