# HIGH remaining after S1–S5b

Scan: scan-2026-09-10T20-03-06.651Z-39e4fa92ce2e

Total HIGH: 118

| File | Line | Class | Title |
|---|---:|---|---|
| benchmark/download_global_top1_benchmarks.py | 29 | path-traversal | 路径穿越 |
| benchmark/extract_gold_anchor_v2.py | 44 | ssrf | SSRF 服务端请求伪造 |
| benchmark/extract_gold_anchor_v2.py | 259 | path-traversal | 路径穿越 |
| benchmark/extract_gold_anchor_v2.py | 274 | path-traversal | 路径穿越 |
| benchmark/run_benchmark_v2.py | 1113 | path-traversal | 路径穿越 |
| benchmark/run_humaneval.py | 34 | ssrf | SSRF 服务端请求伪造 |
| benchmark/run_humaneval.py | 60 | path-traversal | 路径穿越 |
| benchmark/run_humaneval.py | 78 | ssrf | SSRF 服务端请求伪造 |
| benchmark/run_ragas_v1.py | 163 | path-traversal | 路径穿越 |
| benchmark/run_world_exam.py | 27 | ssrf | SSRF 服务端请求伪造 |
| benchmark/run_world_exam.py | 46 | path-traversal | 路径穿越 |
| benchmark/run_world_exam.py | 66 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/ask/route.ts | 60 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/call/session/route.ts | 35 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/health/route.ts | 108 | other-security | probe 是 ssrf 入口 |
| dashboard/src/app/api/scp/health/route.ts | 111 | other-security | probe 是 ssrf 入口 |
| dashboard/src/app/api/scp/health/route.ts | 114 | other-security | probe 是 ssrf 入口 |
| dashboard/src/app/api/scp/health/route.ts | 117 | other-security | probe 是 ssrf 入口 |
| dashboard/src/app/api/scp/v3/hands/planner/status/route.ts | 21 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/v3/hands/status/route.ts | 28 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/v3/pc/status/route.ts | 28 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/v3/web/search/route.ts | 25 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/v3/web/status/route.ts | 28 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/app/api/scp/voice/route.ts | 45 | ssrf | SSRF 服务端请求伪造 |
| dashboard/src/lib/audit-data/round9.ts | 415 | command-injection | 命令注入 |
| mini-services/llm-bridge/core.ts | 537 | ssrf | SSRF 服务端请求伪造 |
| mini-services/llm-bridge/core.ts | 652 | other-security | fetchWithTimeout 是 ssrf 入口 |
| reports/pytest-basetemp/test_parameterize_sql_emits_pa0/victim.py | 2 | sql-injection | SQL 注入 |
| reports/pytest-basetemp/test_sql_scanner_still_flags_r0/victim.py | 4 | sql-injection | SQL 注入 |
| scp/api/routes/v104_routes.py | 121 | ssrf | SSRF 服务端请求伪造 |
| scp/autofix/ast_diff_cache.py | 187 | path-traversal | 路径穿越 |
| scp/autofix/callgraph_delta.py | 398 | path-traversal | 路径穿越 |
| scp/autofix/engine_extensions.py | 94 | path-traversal | 路径穿越 |
| scp/autofix/evolution_modes/__init__.py | 122 | sql-injection | SQL 注入 |
| scp/autofix/evolution_modes/__init__.py | 133 | sql-injection | SQL 注入 |
| scp/autofix/evolution_modes/pattern_fixers.py | 122 | sql-injection | SQL 注入 |
| scp/autofix/evolution_modes/pattern_fixers.py | 133 | sql-injection | SQL 注入 |
| scp/autofix/llm_fix_cache.py | 181 | path-traversal | 路径穿越 |
| scp/autofix/llm_fix_parts/_call_openrouter.py | 56 | ssrf | SSRF 服务端请求伪造 |
| scp/autofix/path_guard.py | 6 | path-traversal | 路径穿越 |
| scp/autofix/policy_gate.py | 126 | ssrf | SSRF 服务端请求伪造 |
| scp/autofix/policy_gate.py | 362 | path-traversal | 路径穿越 |
| scp/autofix/repro_generator.py | 23 | path-traversal | 路径穿越 |
| scp/autofix/restricted_exec.py | 180 | code-injection | 代码注入 |
| scp/autofix/runner_phases/diff_rescan.py | 104 | path-traversal | 路径穿越 |
| scp/autofix/runner_phases/shadow_canary.py | 452 | path-traversal | 路径穿越 |
| scp/autofix/scanners/_self_audit.py | 64 | sql-injection | SQL 注入 |
| scp/autofix/scanners/resource_leak_scanner.py | 14 | ssrf | SSRF 服务端请求伪造 |
| scp/autofix/scanners/resource_leak_scanner.py | 23 | ssrf | SSRF 服务端请求伪造 |
| scp/autofix/speculative_branching.py | 32 | path-traversal | 路径穿越 |
| scp/autofix/speculative_branching.py | 46 | path-traversal | 路径穿越 |
| scp/autofix/speculative_prefixer.py | 540 | path-traversal | 路径穿越 |
| scp/benchmark/benchmark_suite.py | 82 | path-traversal | 路径穿越 |
| scp/benchmark/compare_results.py | 183 | path-traversal | 路径穿越 |
| scp/benchmark/question_generator.py | 341 | path-traversal | 路径穿越 |
| scp/benchmark/question_generator.py | 345 | path-traversal | 路径穿越 |
| scp/benchmark/run_baseline.py | 90 | ssrf | SSRF 服务端请求伪造 |
| scp/benchmark/run_baseline.py | 95 | ssrf | SSRF 服务端请求伪造 |
| scp/benchmark/run_baseline.py | 265 | path-traversal | 路径穿越 |
| scp/benchmark/run_benchmark.py | 251 | path-traversal | 路径穿越 |
| scp/benchmark/run_benchmark_enhanced.py | 512 | path-traversal | 路径穿越 |
| scp/benchmark/run_benchmark_v2_parts/main.py | 165 | path-traversal | 路径穿越 |
| scp/core/data_partitioner.py | 213 | path-traversal | 路径穿越 |
| scp/core/multi_source_verifier.py | 324 | ssrf | SSRF 服务端请求伪造 |
| scp/core/partition/archive.py | 385 | path-traversal | 路径穿越 |
| scp/core/partition/archive.py | 430 | path-traversal | 路径穿越 |
| scp/core/partition/rotate.py | 96 | sql-injection | SQL 注入 |
| scp/core/startup_optimizer.py | 144 | path-traversal | 路径穿越 |
| scp/core/startup_optimizer.py | 298 | path-traversal | 路径穿越 |
| scp/foundation/batch.py | 78 | ssrf | SSRF 服务端请求伪造 |
| scp/foundation/batch.py | 111 | ssrf | SSRF 服务端请求伪造 |
| scp/foundation/batch.py | 138 | ssrf | SSRF 服务端请求伪造 |
| scp/foundation/batch.py | 162 | ssrf | SSRF 服务端请求伪造 |
| scp/foundation/batch.py | 210 | ssrf | SSRF 服务端请求伪造 |
| scp/knowledge/domain_store.py | 335 | path-traversal | 路径穿越 |
| scp/knowledge/issue_parser.py | 11 | ssrf | SSRF 服务端请求伪造 |
| scp/meta/behavior_monitor.py | 415 | path-traversal | 路径穿越 |
| scp/meta/multi_llm_check.py | 120 | ssrf | SSRF 服务端请求伪造 |
| scp/meta/multi_llm_check.py | 157 | ssrf | SSRF 服务端请求伪造 |
| scp/runtime/storage_manager.py | 328 | path-traversal | 路径穿越 |
| scp/security/attack_crawler.py | 172 | ssrf | SSRF 服务端请求伪造 |
| scp/security/attack_crawler.py | 191 | ssrf | SSRF 服务端请求伪造 |
| scp/security/attack_crawler.py | 284 | ssrf | SSRF 服务端请求伪造 |
| scp/security/attack_memory.py | 478 | path-traversal | 路径穿越 |
| scp/security/auto_payload_generator.py | 236 | path-traversal | 路径穿越 |
| scp/security/counter_response.py | 147 | ssrf | SSRF 服务端请求伪造 |
| scp/security/counter_response.py | 190 | ssrf | SSRF 服务端请求伪造 |
| scp/security/os_sandbox.py | 249 | path-traversal | 路径穿越 |
| scp/security/threat_detector.py | 79 | code-injection | 代码注入 |
| scp/task_kernel_parts/taskkernel.py | 309 | sql-injection | SQL 注入 |
| scp/task_kernel_parts/taskkernel.py | 311 | sql-injection | SQL 注入 |
| scripts/diagnostics/count_kb_r37.py | 15 | sql-injection | SQL 注入 |
| scripts/history/r44_build_regression_corpus.py | 36 | sql-injection | SQL 注入 |
| scripts/learning/learning_staging_r43.py | 65 | sql-injection | SQL 注入 |
| scripts/ops/scp_db_consistent_snapshot.py | 62 | sql-injection | SQL 注入 |
| scripts/ops/scp_db_readonly_audit.py | 28 | sql-injection | SQL 注入 |
| scripts/ops/scp_hourly_monitor.py | 68 | ssrf | SSRF 服务端请求伪造 |
| scripts/prep_quick_exam.py | 16 | path-traversal | 路径穿越 |
| scripts/run_full_audit.py | 88 | path-traversal | 路径穿越 |
| scripts/run_full_audit.py | 96 | ssrf | SSRF 服务端请求伪造 |
| scripts/run_full_audit.py | 108 | ssrf | SSRF 服务端请求伪造 |
| scripts/scp_local_bridge.py | 41 | ssrf | SSRF 服务端请求伪造 |
| scripts/scp_local_bridge.py | 60 | ssrf | SSRF 服务端请求伪造 |
| scripts/scp_local_bridge.py | 84 | ssrf | SSRF 服务端请求伪造 |
| tools/build_canonical_text_corpus_all_v2.py | 20 | ssrf | SSRF 服务端请求伪造 |
| tools/build_canonical_text_corpus_v1.py | 9 | ssrf | SSRF 服务端请求伪造 |
| tools/create_and_run_standard_batch.py | 19 | path-traversal | 路径穿越 |
| tools/create_and_run_standard_batch.py | 21 | ssrf | SSRF 服务端请求伪造 |
| tools/fetch_canonical_sources_v1.py | 9 | ssrf | SSRF 服务端请求伪造 |
| tools/fix_same_gt_sources.py | 23 | ssrf | SSRF 服务端请求伪造 |
| tools/refill_bing_real_rag.py | 22 | ssrf | SSRF 服务端请求伪造 |
| tools/run_bounded_system_smoke.py | 44 | ssrf | SSRF 服务端请求伪造 |
| tools/run_canonical_1000_abstain_pipeline.py | 14 | ssrf | SSRF 服务端请求伪造 |
| tools/run_independent_gold_review_v1.py | 17 | ssrf | SSRF 服务端请求伪造 |
| tools/run_local_rag_answer_drafts_v1.py | 22 | ssrf | SSRF 服务端请求伪造 |
| tools/run_scp_full_runtime_rag_1000_v1.py | 20 | ssrf | SSRF 服务端请求伪造 |
| tools/run_standard_rag_pipeline_parallel.py | 27 | ssrf | SSRF 服务端请求伪造 |
| tools/scp_dashboard_bridge.py | 53 | ssrf | SSRF 服务端请求伪造 |