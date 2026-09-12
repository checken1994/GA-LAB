# SCP Reality Verification — S-B3 print→logging (Track B3)

## Claim

Product-runtime `print()` trong `scp/` (ngoại trừ `scp/tests/`, CLI entrypoint,
benchmark stdout, docstring examples) được convert sang `logging` qua logger đã
tồn tại của từng module; message giữ nguyên; pytest baseline không suy giảm;
census cuối = số KEEP đã triage (không còn CONVERT sót).

## Scope

| Trường | Giá trị |
|---|---|
| Branch | `audit/runtime-guard-AUDIT-20260909` |
| Commit đầu S-B3 | `ec03825` (trên nền `89e6a8d` của S-B1c) |
| Commit cuối (snapshot) | `6e99e7a` |
| Test profile | `python -m pytest tests/T03_capability/ tests/T02_contract/ -q` |
| Thời điểm | 2026-09-12 |
| Skill DNA | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` (.agents/skills/scp-dna/SKILL.md) |
| Skill Reality Verifier | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` (.agents/skills/scp-reality-verifier/SKILL.md) |

## Census (rg "^\s*print\(" scp/ -g "*.py")

| Trạng thái | Baseline | Final |
|---|---:|---:|
| Tổng print hits (71 file) | 924 | **842** |
| CONVERT đã sửa | — | **82** |
| KEEP — scp/benchmark/* (stdout = kết quả benchmark) | 191 | 191 |
| KEEP — scp/tests/* (out-of-scope) | 7 | 7 |
| KEEP — scp/__main__.py (CLI entrypoint) | 2 | 2 |
| KEEP — scp/meta/why_engine_cli.py (CLI, `main()` được why_engine.py:92 gọi vào chuỗi CLI) | 26 | 26 |
| Docstring usage examples (regex false-positive, không phải statement) | 8 | 8 |
| KEEP — CLI/demo self-test chain trong product modules (chỉ chạy qua `python -m`, đã verify không có caller runtime) | 608 | 608 |

Delta: 924 − 842 = 82 = đúng số CONVERT đã sửa. Census regex đếm cả docstring —
8 hit false-positive đã đối chiếu thủ công (policy_gate:91, shadow_canary:78,
type_flow_verifier:67, property_validator:73, speculative_prefixer:78,
scpv14_process_mixin:55, callgraph_delta:80+84 — đều là ví dụ usage trong docstring).

## Triage

### CONVERT (82) — product runtime, print thay log

| File | Số print | Bằng chứng runtime | Mức log |
|---|---:|---|---|
| scp/meta/meta.py | 36 | `MetaCognitionEngine.run_meta_cycle()` gọi từ `scpv14_process_mixin.py:601` | info; `except` → error |
| scp/prediction/predictive.py | 36 | `run_cycle()` gọi từ API route `prediction_routes.py:72`; `crawl_all` từ `run_cycle:803`; `verify_pending` từ `prediction_routes.py:103` | info/error theo message ([FAIL] → error) |
| scp/core/hypothesis_zone.py | 3 | `init_hz_schema`, `HypothesisStore.add_partial` (runtime DB path) | info/error |
| scp/core/anchor.py | 1 | auto-init on import — duplicate của `logger.warning` ngay trên | debug |
| scp/core/antibody.py | 1 | auto-init on import — duplicate của `logger.warning` ngay trên | debug |
| scp/core/phase0.py | 1 | auto-init on import — duplicate của `logger.warning` ngay trên | debug |
| scp/autofix/parallel_scanner.py | 1 | worker `_scan_one_file_worker` fail-loudly path (stderr → logger.error, giữ DNA #7 scream) | error |
| scp/runtime/judge_llm.py | 1 | `_llm_judge` except path | error |
| scp/runtime/judge_parts/phases/phase4_call_slms.py | 2 | debug print `file=sys.stderr`, gate `SCP_DEBUG_CONF` giữ nguyên | debug |

### KEEP (760 statements + 8 docstring hits + 7 scp/tests) — có lý do ghi

- **benchmark (191):** run_benchmark_v2_parts/main.py:64, run_benchmark_enhanced.py:39,
  run_benchmark.py:33, run_baseline.py:23, compare_results.py:17,
  evaluate_attacks_v2.py:5, benchmark_suite.py:4, evaluate_questions_v2.py:3,
  question_generator.py:3 — stdout là interface/kết quả benchmark.
- **scp/tests (7):** out-of-scope theo ràng buộc task.
- **CLI entrypoint (2):** scp/__main__.py.
- **CLI tool (26):** scp/meta/why_engine_cli.py (`main()` được why_engine.py:92 import vào CLI).
- **Docstring examples (8):** 7 file liệt kê trên — không phải statement thật.
- **CLI/demo self-test chain trong product modules (608):** print nằm trong
  `if __name__ == "__main__"` guard hoặc trong `main()`/`_smoke_test()` CHỈ được
  gọi từ guard đó — stdout là interface của demo/self-test. Đã verify từng nhóm
  bằng rg callers + AST: falsification_engine(70, `_smoke_test` ← guard 985),
  error_store_index(65, `_smoke_test` ← guard 532), cognitive_engine(32),
  experience.py(26, `run_reflection_cycle` chỉ gọi từ `main()` argparse 817/822),
  auto_backup(20), data_partitioner(22, guard), multi_source_verifier(20),
  crypto_verifier(19), verdict_predictor(18), policy_applier(18), question_tracker(22,
  `print_summary_table` chỉ gọi từ CLI main:456), calibration_engine(16),
  circuit_breaker(15), startup_optimizer(14, guard), principle_rules(14),
  live_knowledge(14), smart_classifier(11, guard), response_monitor(21, guard),
  multi_turn_tracker(11, guard), source_watchlist(13, guard), source_reputation(11,
  guard), behavior_monitor(11, guard), smart_cache(10), conflict_resolver(9),
  runner.py(9, `_main` ← guard 731), cross_language_learner(8, guard),
  math_evaluator(8, guard), simple_explainer(7, guard), real_question_fetcher(7),
  realtime_verifier(6, guard), image_voice_detector(6, guard), attack_crawler(5,
  guard), auto_payload_generator(5, guard), reverify_scheduler(5), streaming_factcheck(5,
  guard), domain_classifier(2), _self_audit(1, `run_self_audit_cli` ← guard),
  bounded_evolution(1, guard), kernel_patrol(1, guard), deterministic_worker(1,
  `_main` ← guard 544)…

## Fix method

- Fixer AST-informed (script tạm ngoài repo, KHÔNG commit): parse AST, phân loại
  print theo ngữ cảnh (`__main__` guard / skip-fn {main, _smoke_test,
  run_self_audit_cli} / except handler / khác), thay token `print(` tại đúng
  (line, col) của Call node bằng `logger.<level>(`; skip print có kwargs
  (`file=`/`end=`...) để xử lý thủ công. Level: DBG/ERR/WARN keyword trên text
  arg đầu → debug/error/warning; trong `except` không keyword → error; còn lại → info.
- 4 print duplicate auto-init (anchor/antibody/phase0/hypothesis_zone module-level)
  → `logger.debug` thủ công: đã có `logger.warning(..., exc_info=True)` fail-loudly
  ngay phía trên (S-B1c), tránh double-log cùng sự kiện ở level cao.
- phase4_call_slms: giữ gate `os.environ.get('SCP_DEBUG_CONF')`, bỏ `import sys`
  cục bộ + `file=sys.stderr` → `logger.debug`.
- Tất cả 14 file xét đến ĐÃ có `import logging` + `logger` từ trước → không inject
  import mới. Message giữ nguyên (f-string giữ nguyên trong log call).

## Evidence chain — commits (per-module)

| Module | Số convert | Commit |
|---|---:|---|
| scp/meta (meta.py) | 36 | `ec03825` |
| scp/prediction (predictive.py) | 36 | `4bc5cb4` |
| scp/autofix (parallel_scanner.py) | 1 | `fe6bc88` |
| scp/core (hypothesis_zone, anchor, antibody, phase0) | 6 | `e2d5f66` |
| scp/runtime (judge_llm, phase4_call_slms) | 3 | `6e99e7a` |

py_compile: 9/9 file converted PASS (`python -m py_compile ...` → ALL-COMPILE-OK).

## Pytest (tests/T03_capability/ + tests/T02_contract/)

| Lần | Kết quả | Chi tiết |
|---|---|---|
| Baseline TRƯỚC (run 1) | 2 failed, 861 passed, EXIT=1 | tail chỉ hiện `test_hands_authority_pep.py::test_bridge_execute_missing_token_clean_policy_denial_no_recovery` |
| Baseline TRƯỚC (run 2, -p no:randomly) | 3 failed, 860 passed, EXIT=1 | + `test_flow_08...test_audit_stats_requires_admin`, `test_audit_findings_requires_admin` |
| SAU (run 3) | **1 failed, 862 passed, EXIT=1** | chỉ `test_hands_authority_pep.py::test_bridge_execute_missing_token...` |

Baseline fail set là FLAKY pre-existing: {flow_08 audit admin ×2, hands_authority_pep
×1} — biến thiên 1–3 giữa các run TRƯỚC khi có thay đổi. Fail set SAU ⊆ baseline
set → **fail không tăng** (PASS_WITHIN_SCOPE: không quy kết nguyên nhân, chỉ ghi
quan sát; không test nào trong scope dùng capsys/capfd/redirect_stdout — `rg` = 0).

## Postconditions

| Điều kiện | Quan sát | Verdict |
|---|---|---|
| Census delta = số convert | 924→842, delta 82 = 36+36+1+6+3 | VERIFIED |
| Không còn CONVERT sót trong scp/ | Tất cả print còn lại mapped vào KEEP có lý do ghi | VERIFIED (theo triage hiện tại) |
| Message giữ nguyên | Diff review thủ công từng file | VERIFIED |
| pytest không suy giảm | 1 failed ⊆ baseline flaky set {1–3} | VERIFIED trong scope |
| py_compile sạch | 9/9 OK | VERIFIED |

## Limitations

- KEEP-câu 608 CLI/demo self-test: triage dựa trên verify callers hiện tại; nếu
  sau này product code bắt đầu gọi `main()`/`_smoke_test()` của các module này
  tại runtime, cần đánh giá lại (đã ghi vào bảng).
- Level mapping info/warning/error mang tính phán đoán ngữ nghĩa từ text; không
  có spec chính thức cho từng message. Chỉ 4 chỗ chủ ý hạ xuống debug (duplicate).
- pytest profile chỉ gồm T03_capability + T02_contract; không chạy full suite.
- Fixer script nằm ngoài repo (/tmp) nên không tái hiện được bằng artifact commit;
  logic được mô tả đầy đủ ở mục "Fix method", kết quả kiểm chứng bằng census +
  diff + py_compile + pytest.

## Final verdict

VERIFIED_WITHIN_SCOPE — 82 product-runtime print đã convert sang logging (5
commits per-module), census cuối khớp triage, pytest không suy giảm so với
baseline flaky. Không tuyên bố "toàn bộ scp/ không còn print" (còn 608 print
CLI/demo self-test được KEEP có lý do ghi, trừ scp/tests out-of-scope).
