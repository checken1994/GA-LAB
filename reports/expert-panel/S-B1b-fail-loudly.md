# S-B1b — Fail-loudly census + fix cho `scp/autofix/` và `scp/runtime/`

- Agent: S-B1b (Track B1 fail-loudly, lô 2 — tiếp nối S-B1a)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`
- Base commit: `25515ea` (docs(S-B1a): record fail-loudly census + module fix report)
- Ngày: 2026-09-12
- Scope: CHỈ `scp/autofix/` + `scp/runtime/` (bao gồm thư mục con: `engine_parts/`,
  `scanners/`, `scanner parts`, `runner_phases/`, `evolution_parts/`, `llm_fix_parts/`,
  `experts/`, `slm_impls/`, `slms_parts/`, `judge_parts/`). KHÔNG đụng tests/, GA.md,
  circuit-closures, dashboard, mini-services, core/meta/security/knowledge.
  Verify: `git diff 25515ea..HEAD --name-only | grep -cv '^scp/autofix/\|^scp/runtime/'` = **0**.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## 1. Census (baseline của lô)

Script tái sử dụng từ S-B1a: `scripts/diagnostics/census_silent_except.py`
(classifier SILENT = body không có logger-call / raise / return-lỗi-tường-minh /
comment `# silent-by-design`). Script có `SCOPES` hardcode (`scp/core`, `scp/meta`)
nên lô này **import module và override SCOPES tại runtime** — không sửa file script.

Baseline trên 2 scope (1042 handler):

| Nhóm | autofix | runtime | Tổng |
|---|---:|---:|---:|
| OK (has log/raise/explicit error return) | | | 799 |
| INTENTIONAL (silent-by-design) | 0 | 0 | 0 |
| **SILENT (cần fix)** | **150** | **93** | **243** |

Baseline evidence: `reports/expert-panel/S-B1b-census-baseline.json` (commit kèm report).

## 2. Fix theo module (commit per module, file lớn trước)

| Commit | Module | Blocks | Files |
|---|---|---:|---:|
| `00efa0f` | autofix engine group: `engine.py`, `engine_extensions.py`, `engine_parts/{autofix_mixin,verify_mixin}.py` | 17 | 4 |
| `d6b6808` | autofix `scanners/` (dead_code×4 site, hypothesis, _self_audit, + 11 scanner parse-probe) | 42 | 15 |
| `9f87e54` | autofix `runner.py` + `runner_phases/` (ast_scan, blast_radius, completeness_check, reality_test, shadow_canary) | 18 | 6 |
| `ede8d0e` | autofix `policy_gate.py` + `shadow_snapshot.py` | 19 | 2 |
| `996d867` | follow-up: placement comment policy_gate (1 block sót do comment 2 dòng) | 1 | 1 |
| `2a1e4b1` | autofix evolution group: `evolution.py`, `evolution_parts/{buildmixin,reflectmixin}.py` | 8 | 3 |
| `aef5107` | autofix file vừa: callgraph_delta, property_validator, type_flow_verifier, deterministic_worker, enterprise_scanners, intent_inference_engine | 27 | 6 |
| `265ea20` | autofix file nhỏ (14 file: ast_diff_cache, audit_log, bug_report_validator, concurrent_runner, confidence_ranker, deterministic_patches, llm_fix_cache, llm_fix_parts×2, parallel_scanner, path_guard, realtime_verifier, speculative_prefixer, validate_patch) | 19 | 14 |
| `fd35b36` | runtime slm group: `slm_base.py`, `slm_impls/`×5, `slms_parts/`×5 | 47 | 11 |
| `77323e8` | runtime `experts/`×5 | 24 | 5 |
| `df105e2` | runtime judge group: `judge.py`, `judge_llm.py`, `judge_parts/`×6 | 19 | 8 |
| `e6d8919` | runtime misc: multi_llm_crosscheck, notifications, timing_and_restart | 3 | 3 |

Tổng: **243 block xử lý trong 77 file** (+471/−127; 12 commit). Không bỏ block nào —
census cuối cả 2 scope = **0 SILENT**, không còn dư cho lô sau.

Phân bố xử lý theo mức nghiêm trọng (áp scp-dna + reality-verifier):

- **Rollback path nuốt exception = nghiêm trọng → `logger.critical`/`logger.warning`
  + trạng thái rõ** (đúng hướng dẫn lô):
  - `autofix_mixin.py` 5 site shadow-rollback nuốt exception của chính nó:
    4× `logger.warning` (part1/2/3 non-fixed, fell-through — tx còn lại trong
    active dir, GC sẽ dọn) + 1× `logger.critical` (auto-fix crash VÀ rollback
    cũng fail = double failure, cần dọn thủ công).
  - `shadow_snapshot.py`: atomic-replace fail trong rollback-restore →
    `logger.warning` trước khi rơi vào copy-fallback (rollback phải thấy được).
  - Git-rollback-token failover sang backup-token (`autofix_mixin`) → `logger.warning`.
- **Verification/query path không được giả "sạch"** → `logger.warning`, giữ return contract:
  `ast_scan._scan_file` (crash → []), `enterprise_scanners` secret-scan read,
  `evolution._count_bugs` (crash → 0 bug), `callgraph_delta.get_calls_in_file`,
  `shadow_canary._detect_exception_regression` (crash so sánh → "no regression"
  phải hiện ra), `deterministic_worker._decision_is_logged` (OSError audit log).
- **Security path**: `policy_gate.matches()` regex lỗi → `logger.error`
  (pattern hỏng = rule bị tắt ngầm; giữ contract False).
- **Parse-probe/optional-fallback/best-effort có documented default** →
  `logger.debug` + `# silent-by-design: <lý do>` (pattern đồng nhất ở scanners:
  "skipping unparseable/unreadable file"; ở slm/experts: lỗi external fetch ĐÃ
  được mang trong `reasoning` + `confidence=0` trả về caller → comment-only).
- **Explicit error return/record**: `(False, reason)`, `{'status':'blocked',
  'reason':...}`, `result.error`, `attempt{'provider':'error:...'}`,
  `node.parse_error`, `restore_errors` → comment-only (lỗi đã tường minh qua
  cấu trúc trả về — tương tự precedent `data_partitioner` của S-B1a).
- Re-raise: 0 block — không có rollback/security path nào trong scope này mà
  contract hiện tại cho phép raise; các path fail-closed (path_guard None,
  property_validator "outputs differ", reality_test KeyboardInterrupt) đã giữ
  hướng an toàn và được ghi reason.

Module thêm logger mới: `reality_test.py` (đổi: handler cần debug),
`llm_fix_parts/_generate_deterministic_fix.py` + `llm_fix_parts/generate_fix_for_bug.py`
(phát hiện thêm: 2 file auto-extract từ `llm_fix.py` **mất hẳn định nghĩa
`logger`** dù body vẫn gọi `logger.debug/info` → NameError tiềm ẩn tại runtime;
đã thêm `logging.getLogger(...)` — sửa đúng PRODUCT tại điểm lỗi, không phải chỉ
để census xanh).

Lưu ý shape hygiene (riêng autofix): mọi comment mới là văn bản thuần
(không chứa token dạng code như `(`-call pattern, không URL, không `verify`-style
flag) — không thêm pattern nguy hiểm vào comment/docstring của scanner.

Census-classifier nuance (ghi để tái lập): phrase `silent-by-design` phải nằm
trên dòng kề trên statement đầu tiên của handler (hoặc inline cùng dòng) —
comment nhiều dòng đặt phrase ở dòng đầu khối sẽ không được nhận diện. Đã phát
sinh 3 follow-up nhỏ trong quá trình làm; tất cả đã về 0 trước khi commit module
kết thúc (riêng M4: 1 block sót bị commit kèm `ede8d0e`, sửa ngay bằng `996d867`).

## 3. Census sau fix

```
TOTAL except handlers: 1042
OK(has log/raise): 903
INTENTIONAL(silent-by-design): 139
SILENT(need fix): 0
```

(autofix riêng: 0 SILENT / 498 OK / 46 INTENTIONAL tại thời điểm giữa lô; cả 2 scope 0 SILENT ở census cuối.)

## 4. Verify (pytest + py_compile)

Baseline (chạy trước fix đầu tiên, tại `25515ea`):
`python -m pytest tests/T03_capability/ tests/T07_learning/ -q` →
**5 failed / 728 passed, EXIT=1**.

Lưu ý: con số hint trong task ("~3F/950P+") không khớp reality chạy tại máy —
theo DNA #26, lấy run thực tế làm baseline. 5 fail baseline gồm (từ log):
2× `test_flow_08_audit_benchmark_scp_standard` (order-dependent flaky, S-B1a
đã ghi nhận), `test_hands_authority_pep::test_bridge_execute_missing_token_...`
(pre-existing từ S-B1a), 2× `test_autofix_shadow_rollback::test_verify_fix_pytest_gate_*`
(nằm ngay trong scope lô này — là pre-existing tại baseline, KHÔNG được làm tăng).

| Lần chạy | Commit điểm | Kết quả |
|---|---|---|
| Baseline (trước fix đầu) | `25515ea` | 5 failed / 728 passed, EXIT=1 |
| Giữa lô (sau toàn bộ autofix M1–M7) | `265ea20` | 5 failed / 728 passed (= baseline) |
| Cuối lô (sau toàn bộ runtime M8–M11) | `e6d8919` | 5 failed / 728 passed (= baseline) |

Gate: **fail KHÔNG tăng so baseline** (5 = 5, xác nhận 2 lần sau fix).

`py_compile` PASS: từng file sau mỗi module + sweep cuối toàn bộ **77 file**
(`PYCOMPILE_SWEEP_OK x77`).

## 5. Limitations / open questions (DNA #22, #23)

- Census chỉ quét `except` block trong `scp/autofix/` + `scp/runtime/`;
  silent-failure dạng khác (`contextlib.suppress`, return-code bỏ qua, stderr
  nuốt) chưa thuộc census — `parallel_scanner` (stderr-scream per DNA #7) và
  `file_mutex`-style suppress đã thấy nhưng giữ nguyên contract.
- `logger.debug` cần log-config phù hợp mới nhìn thấy ở production; chưa audit
  cấu hình logging toàn cục (ngoài scope).
- 2 test `test_autofix_shadow_rollback` fail từ baseline — thuộc verify/rollback
  path của autofix nhưng là pre-existing; xử lý chúng thuộc task sửa product
  riêng, không phải lô census này (không đụng tests/).
- Bằng chứng ở đây: static census (máy-checkable) + unit-test profile T03+T07
  (cấp A/B theo reality-verifier). Chưa có integration/end-to-end proof (cấp C/D).
- `PASS_WITHIN_SCOPE` của census 0-SILENT + pytest-not-worse tại commit
  `e6d8919`; không claim gì vượt phạm vi này.

## 6. Evidence files

- Census script (tái dùng, không sửa): `scripts/diagnostics/census_silent_except.py`
- Baseline census JSON: `reports/expert-panel/S-B1b-census-baseline.json`
- Patch scripts (tái lập, đặt ngoài repo trong TEMP, không commit vào repo):
  `s_b1b_scanners_patch.py`, `s_b1b_runtime_patch.py`
- pytest logs: session logs của các run baseline/mid/final nêu ở mục 4.
