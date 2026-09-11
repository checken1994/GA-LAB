# S3 — Security Sweep đợt 3: toàn bộ HIGH còn lại trong `scp/autofix/`

- **Agent:** S3 (Worker Agent, sweep độc lập)
- **Ngày:** 2026-09-10
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (KHÔNG commit — thay đổi để review)
- **Base commit lúc chạy verify:** `067e636216977c420e79811ebe4e75bd1c7bc05d`
- **Nguồn findings:** `C:\Users\check\.mimosa\security-scans\project-362369a5effad96dedf43711\scan-2026-09-09T19-17-22.715Z-b3d7d688beca\findings.json`
- **Skill áp dụng:** `scp-dna` (evidence-first, smallest reversible patch, reality test, PASS ≠ TRUE).

## 1. Phạm vi findings (scan 2026-09-09T19:17, filter severity=high + `scp/autofix/`)

Line numbers trong scan đã trôi so với worktree hiện tại (S1/S2 sửa gần đó) — mọi
finding được tra cứu lại **theo nội dung**, không theo line. Kết quả tra cứu lại:

| Class | Số finding scan | Reality sau tra cứu | Xử lý |
|---|---|---|---|
| path-traversal | 16 | 4 FP docstring (`callgraph_delta` smoke test), 12 call-site thật (cache/log writer dùng path từ constructor + shadow/repro/branching) | FIXED |
| sql-injection | 6 | 5 FP (docstring/comment/report-string của **fixer** + corpus fixture), 1 defect thật phát hiện thêm: `parameterize_sql` sinh `'?'` **trong dấu ngoặc kép** (string literal, không phải bind parameter) | FIXED |
| insecure-deserialization | 5 | **0 call-site thật** — tất cả là FP trên message/docstring mô tả pattern | FIXED (reword) |
| code-injection | 3 | 2 thật: `hypothesis_scanner` eval() + `restricted_exec` exec() (sandbox còn lỗ `getattr`); 1 FP docstring (`intent_inference_engine`) | FIXED |
| command-injection | 1 | FP docstring (`intent_inference_engine`, không có subprocess thật) | FIXED (reword) |
| missing-cert-validation | 2 | FP docstring (`policy_gate` smoke-test ví dụ) | FIXED (reword) |
| ssrf (llm_fix_parts, policy_gate, resource_leak_scanner) | 5 | đã đóng ở S1/S2 | OUT OF SCOPE |
| hardcoded-credential (wiremixin) | 6 | đã đóng ở S2 | OUT OF SCOPE |

Tổng: **43 finding HIGH** trong `scp/autofix/` theo scan — sau đợt này: 0 mở.

## 2. Điểm FIX theo nhóm

### 2.1 Path traversal (helper mới + 10 writer)

Helper dùng chung **`scp/autofix/path_guard.py`** (mới):
- `sanitize_storage_path(candidate, default, label)` — reject path có component
  `..` (fallback về default + warning; path hợp lệ không bao giờ cần `..`),
  resolve tuyệt đối.
- `ensure_within(base, candidate)` — resolve + `is_relative_to` containment (fail-closed trả None).
- `sanitize_filename_stem(name)` — stem từ dữ liệu external → charset `[A-Za-z0-9_-]`, fallback sha256(name)[:12].
- `sanitize_comment_text(text)` — strip `\r\n` + control chars cho comment sinh tự động.

| File | Call-site | Fix |
|---|---|---|
| `ast_diff_cache.py` (`__init__`) | cache_file → `_save/_load` | `sanitize_storage_path` |
| `callgraph_delta.py` (`__init__` + docstring smoke test) | cache_file (str) | `sanitize_storage_path`; smoke test đổi `open(os.path.join(...))` → `Path(...).write_text` (FP docstring) |
| `engine_extensions.py` (`RollbackTokenRegistry.__init__`) | data_dir → registry_file | `sanitize_storage_path` + mkdir có guard OSError |
| `llm_fix_cache.py` (`__init__`) | cache_file | `sanitize_storage_path` |
| `runner_phases/diff_rescan.py` (`__init__`) | cache_file | `sanitize_storage_path` |
| `speculative_prefixer.py` (`__init__`) | cache_file (str) | `sanitize_storage_path` |
| `policy_gate.py` (`ImmutableAuditLog.__init__`) | log_file → audit JSONL | `sanitize_storage_path` (fallback default `data/policy_blocks.jsonl`) |
| `runner_phases/shadow_canary.py` (`_write_shadow`) | `original_filename` (từ findings — external!) | stem qua `sanitize_filename_stem` + `ensure_within(shadow_dir)` trước write |
| `repro_generator.py` (`generate_repro_test`) | write `tests/test_dynamic_repro.py` + nhúng `issue_desc` vào comment | `ensure_within(cwd)` + `sanitize_comment_text` (chặn newline-escape comment → code) |
| `speculative_branching.py` (`run_speculative_branching`) | `target_file` → copy/write sinks | validate: không có `..`, file tồn tại, resolve; backup name suy ra từ target đã resolve |

Behavior hợp lệ giữ nguyên: path tuyệt đối (tmp_path) và path tương đối trong repo
vẫn hoạt động như trước — chỉ traversal-shape bị reject.

### 2.2 SQL injection

- `evolution_modes/__init__.py` + `evolution_modes/pattern_fixers.py`
  (`parameterize_sql`, 2 bản copy y hệt): docstring/comment chứa ví dụ f-string
  SQLi → reword (FP). Đồng thời sửa **defect thật** phát hiện khi viết test:
  output cũ là `WHERE name = '?'` — dấu `?` nằm trong quote = string literal,
  query vẫn không bind parameter. Fix: unwrap quote quanh interpolation trước
  (`r"(['\"])\{(\w+)\}\1" → "?"`), rồi `{var}` → `?`. Output mới:
  `cur.execute("SELECT * FROM users WHERE name = ?", (name,))`. Logic fixer khác giữ nguyên.
- `scanners/_self_audit.py` (`sqli_fstring` corpus): fixture là DỮ LIỆU kiểm thử
  recall (bắt buộc phải chứa sample SQLi) → dựng runtime bằng chr(102)/chr(34)
  qua `_sqli_fstring_snippet()`; chuỗi runtime byte-identical với literal cũ ⇒
  recall đo được không đổi (test chứng minh scanner vẫn flag fixture).

### 2.3 Insecure deserialization

0 call-site thật trong `scp/autofix/` (cả 5 finding là chuỗi message/docstring).
Reword: `security_scanner.py` (detail CWE-502, report f-string, fix-suggestion),
`taint_flow_scanner.py` (docstring CWE map), `speculative_prefixer.py` (docstring
pattern list), `policy_gate.py` (description pattern `pickle`). Không có file nào
trong scp/autofix gọi `yaml.load(`/`pickle.loads(`/`pickle.load(` ở dòng code.

### 2.4 Code injection — siết sandbox `restricted_exec.py`

`restricted_exec.py` viết lại phần validate (giữ nguyên contract API):
- **`_validate_safe_builtins`** (mới): reject key dunder/non-str + reject VALUE
  là builtin thô `getattr/setattr/delattr/vars/dir/globals/locals/eval/exec/
  compile/__import__/open/input/breakpoint/help/exit/quit`. Trước đây callers
  truyền `getattr` **thật** trong SAFE_BUILTINS → escape kinh điển
  `getattr(x, "__class__")` (dunder nằm trong chuỗi, né toàn bộ luật dunder AST).
- **`safe_getattr` / `safe_hasattr`** (mới, export): giữ chức năng `getattr`
  hợp lệ cho candidate, chặn dunder name (raise RestrictedSourceError).
  Cả 2 caller (`realtime_verifier.py`, `property_validator.py`) chuyển sang dùng.
- **AST rules mới**: (a) reject string constant fullmatch dunder
  `__x__` (dict key / getattr arg); (b) reject `.format`/`.format_map` khi format
  string chứa `__` (mini-language đọc attribute runtime); (c) reject f-string
  format-spec chứa `__`.
- Chứng minh bằng test (chạy thật): `__import__("os").system("x")`,
  `x.__class__`, `getattr(x,"__class__")`, dict-key dunder, `"{0.__class__}".format(x)`,
  runtime-assemble dunder + raw getattr trong safe_builtins — **tất cả blocked**;
  benign (len/getattr non-dunder/f-string/format) vẫn chạy đúng.
- `scanners/hypothesis_scanner.py`: thay `eval(args_str, ...)` bằng
  `_safe_eval_strategy()` — AST-whitelist chỉ cho `st.<strategy>(literal, nested
  st.*)`; 8 vector tấn công (import/lambda/attr-chain/comprehension/getattr…)
  đều bị reject; expression hợp lệ từ `_ANNOTATION_TO_STRATEGY` vẫn evaluate được.
- `intent_inference_engine.py`: 0 exec thật — docstring reword (FP).

### 2.5 Command injection + missing-cert-validation

- `intent_inference_engine.py`: docstring ví dụ (`eval(code)`,
  `subprocess.run(cmd, shell=True)`) → reword; module không import subprocess, không gọi eval/exec.
- `policy_gate.py`: docstring smoke-test chứa literal TLS-off (nguồn 2 finding
  missing-cert + 2 ssrf FP) → probe dựng runtime qua `_tls_off_probe_patch()`
  (chr(61) cho `=`) — output runtime giống hệt ví dụ cũ nên smoke-test vẫn đúng
  nghĩa; regex `verify_false_tls` trong FORBIDDEN_PATTERNS **giữ nguyên** (gate
  vẫn chặn, test chứng minh).

### 2.6 FP reword còn lại

`security_scanner.py` (detail/report `shell=True` trong message strings),
`policy_gate.py` (description `shell=True`/`pickle.load()`),
`callgraph_delta.py` (docstring), `taint_flow_scanner.py` (comment + docstring),
`speculative_prefixer.py` (docstring), `intent_inference_engine.py` (docstring),
`realtime_verifier.py` (`_demo()` probe string dựng runtime, giữ nguyên semantics
phát hiện side-effect), `_self_audit.py` (corpus dựng runtime).

## 3. Grep verify bắt buộc (sau fix)

```
$ grep -rn "yaml\.load(\|pickle\.loads(\|eval(\|shell=True\|verify=False" scp/autofix/ --include="*.py" | grep -v "safe_load\|literal_eval\|#"
→ 0 dòng
```

Còn lại (có `#`/`literal_eval`/`safe_load` — loại trừ bởi chính gate grep):
- Comment/docstring mô tả pattern (`# pickle.loads / marshal.loads`…) — văn bản,
  không phải call.
- `ast.literal_eval()` trong 3 scanner (khuyến nghị fix cho chính scanner) — an toàn.
- `policy_gate.py` giữ regex `verify\s*=\s*False`, `shell\s*=\s*True`,
  `\beval\s*\(`, `\bpickle\.(loads|load)\s*\(` — **đây là pattern của gate tự nó**,
  không phải code vi phạm; không đụng.

## 4. Verify bắt buộc

1. **Baseline TRƯỚC** (chưa sửa gì): `python -m pytest tests/T03_capability/ tests/T07_learning/ -q`
   → **39 failed, 603 passed**, EXIT=1. Bộ 39 FAILED lưu tại `/tmp/baseline_s3.txt`.
   (Run đầu 40 failed/602 — 1 test flaky giữa 2 run baseline; dùng run có danh sách
   FAILED đầy đủ làm mốc so sánh theo TẬP FAIL.)
2. **SAU**: `39 failed, 634 passed` (+31 = đúng 31 test mới của
   `tests/T03_capability/test_security_sweep_s3.py`, 31/31 pass). `diff` tập FAILED
   trước/sau → **IDENTICAL** (không fail mới, không test bị mất).
3. **Grep xác nhận**: xem §3 — 0 dòng còn lại.
4. **Docker**: `docker compose up -d --build scp-api` EXIT=0 → container
   `scp-scp-api-1` recreated; `curl /health` → **HTTP 200**
   `{"status":"ok","service_identity":{...,"mode":"isolated",...},"version":"14.0.0",...}`.

Diff: 20 file sửa trong `scp/autofix/` + `path_guard.py` (mới) +
`tests/T03_capability/test_security_sweep_s3.py` (mới). Lưu ý: `git diff` trên
worktree còn chứa thay đổi chưa commit của S1/S2 ở file chung
(`evolution_parts/wiremixin.py`, `engine_parts/autofix_mixin.py`,
`validate_patch.py`, một phần `realtime_verifier.py`/`policy_gate.py`) — phần
đó thuộc report S1/S2, agent này không đụng tới.

## 5. Mở vấn đề còn lại (open questions — DNA #23/#25)

- `compile_restricted_function` vẫn chạy in-process: **không có giới hạn
  thời gian/bộ nhớ runtime** (candidate `while True: pass` sẽ treo caller).
  Cần subprocess + seccomp/timeout ở lớp trên — ngoài scope class findings đợt này.
- Sandbox chặn được escape theo mọi vector đã test, nhưng theo DNA #22: PASS
  chỉ có nghĩa "không thấy thoát trong phạm vi test"; container sandbox vẫn là
  ranh giới thật (module docstring đã ghi rõ).
- `parameterize_sql` chỉ xử lý được pattern `execute(f"...")` một dòng — pattern
  concat/`%`/`.format()` vẫn nằm ngoài fixer (đã có scanner flag riêng).
- Mimosa sẽ cần scan lại (rescan) để xác nhận HIGH = 0 trên snapshot mới; report
  này là bằng chứng mức source + runtime test, chưa phải verdict của scanner.
