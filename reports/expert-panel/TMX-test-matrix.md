# TMX — Test Matrix: product fix → pinning test (campaign AUDIT-20260909)

- Agent: TMX (Test Matrix Worker)
- Date: 2026-09-12
- Branch/HEAD at start: `audit/runtime-guard-AUDIT-20260909` @ `c9955e1`
- Range audited: `git log 1f00d00..HEAD` (M02 pin → M14+ closure) + `reports/circuit-closures/M02..M14-closure.json` + `reports/expert-panel/DNA1/DNA2-compliance.md`
- Method (FA-13 causal coverage + DNA #22): for every fix commit, the diff (`git show <sha> -- <file>`) was read to extract the exact new contract, then `tests/` was grepped for an assertion that would FAIL if the product reverted to the pre-fix behavior. A row is PINNED only when a concrete test name pins the post-fix contract; PASS-without-pin does not count.

## Mandatory skill binding (SHA256, read at session start)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

Evidence levels per scp-reality-verifier: product-fix pins marked "runtime" are behavioral (B-level integration through real pipeline / real DB / real HTTP fixture); "(TMX-NEW)" rows were added by this task and executed green at the commit recorded below. DNA #22: each pin asserts the post-fix behavior on the branch that the bug used to break.

## Matrix — product behavior fixes (35 rows)

Legend: PIN = pinned by pre-existing test; TMX = cell was MISSING, patched by this task; fix commits are product code unless noted.

### M02 — Ask & Chat (fixes PRE-DATE the audited range)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 1 | Agent-A MACH2 ask/chat fixes closed at sha_pin `1f00d00` | pre-`1f00d00` | `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` (pinned at 1f00d00, re-run green in this session's regression: T02 has 0 failures) | PIN (pre-range) |

### M03 — OpenAI-compat & SWE-bench (`3f29c18`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 2 | Judge failure → structured 503 OpenAI error envelope, no internal-message leak | `3f29c18` | `tests/T02_contract/test_flow_03_openai_compat_scp_standard.py::test_openai_compat_gateway_failure_returns_503` | PIN |
| 3 | Auth-first reality: 401 without auth; schema violation → 400 envelope WITH auth | `3f29c18` | `...flow_03...::test_openai_chat_completions_validates_schema` | PIN |
| 4 | `stream=true` accepted, answered with single JSON (no simulated SSE) | `3f29c18` | `...flow_03...::test_openai_compat_handles_streaming_false`, `::test_streaming_response_translation` | PIN |
| 5 | SWE-bench mounted at real `/swe-bench/v1` prefix + strict OpenAI shape | `3f29c18` | `...flow_03...::test_swe_bench_chat_completions_endpoint_exists` | PIN |
| 6 | `instance_id` accepted+ignored; missing `model` → 422 | `3f29c18` | `...flow_03...::test_swe_bench_validates_instance_id` | PIN |
| 7 | SWE error path = real pydantic 422 + detail (no invented AgentOrchestrator) | `3f29c18` | `...flow_03...::test_swe_bench_compat_agent_failure_returns_error` | PIN |
| 8 | `v105_routes.py` imports `Request` → `app.openapi()` no longer crashes | `3f29c18` | `tests/T02_contract/test_api_import_order_contract.py::test_extra_routers_survive_both_import_orders` | PIN |

### M04 — Control & Hands (`0d13c85`, `e13fad4`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 9 | Bridge fail-closed ordering: PermissionError `CapabilityRequiredError (FA-05)` raised BEFORE registry.require and BEFORE any kernel mutation (incl. unparseable token) | `0d13c85` | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py::test_hands_executor_rejects_missing_token_fail_closed`, `::test_pc_controller_execute_rejects_missing_token` | PIN |
| 10 | Hands route maps PEP rejection → HTTP 403 carrying `CapabilityRequiredError` (was 500) | `e13fad4` | `...flow_04...::test_hands_execute_missing_capability_token_returns_403` | PIN |
| 11 | PC controller token+capability gates; empty state file → fail-closed revoked (state_corrupt) | `0d13c85` | `...flow_04...::test_pc_controller_execute_requires_token_and_capability`, `::test_pc_controller_kill_clear_requires_capability_token` | PIN |
| 12 | Planner preserves capability token (real assertion, not vacuous `or`) | `0d13c85` | `...flow_04...::test_planner_preserves_capability_token_in_steps` | PIN |
| 13 | Hands allowlist contract (`pc.execute` deliberately NOT exposed) + token forwarded | `0d13c85` | `...flow_04...::test_hands_executor_forwards_token_to_controller` | PIN |

### M06 — Prediction (`75e994f`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 14 | Engine singleton wiring: routes read canonical `_predictive_engine` created by `get_judge()` (endpoint 503 → works) | `75e994f` | `...test_flow_06_prediction_scp_standard.py::` `m6_engine` fixture assert + `::test_prediction_run_cycle_executes_v5_pipeline` | PIN |
| 15 | `POST /predictions/verify` accepts `limit` (schema `ge=1`, endpoint no longer 500) | `75e994f` | `...flow_06...::test_prediction_verify_fail_closed_without_real_data` | PIN |
| 16 | QuestionGenerator skips KhamPha specs without `ai_answer`, warning stays observable | `75e994f` | `...flow_06...::test_prediction_run_cycle_executes_v5_pipeline` (caplog assert), `::test_prediction_generate_from_local_data_and_dedup` | PIN |
| 17 | `save_prediction` persists `entity` column (was accepted-but-dropped, silent data loss) + migration | `75e994f` | `...flow_06...::test_save_prediction_persists_entity_column` (TMX-NEW) | TMX |
| 18 | `SelfLearner._get_engine()` dead SCPV13 fallback → real RealityClassifier fallback (Learn phase alive) | `75e994f` | `...flow_06...::test_prediction_learn_updates_model` (TRAINING_DATA grows) | PIN |

### M09 — Threat & Counter (`b4134ac`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 19 | `threat_routes` gated by direct `Depends(verify_admin)`; `check_admin` MagicMock test-hook removed from production auth path; THREAT-5 de-mocked | `b4134ac` | `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py::test_threat_ai_scan_stats_requires_admin` (+3 sibling 401/403 probes), `::test_threat_ai_scan_returns_scan_metrics` (REAL Bearer auth golden path) | PIN |

### M10 — Streaming (`1691f7f`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 20 | `ask_stream` consumes judge DICT contract (`verdict["..."]`), emits real `final` frame with verdict/confidence/dict evidence (was attribute access → AttributeError, no final frame) | `1691f7f` | `tests/T03_capability/test_flow_10_streaming_scp_standard.py::test_stream_endpoint_accepts_streaming_request`, `::test_stream_sse_format_correct`, `::test_stream_handles_llm_gateway_failover` (real judge pipeline, egress-denied offline) | PIN |

### M11 — Admin/Import (`8fc3560`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 21 | `POST /import/jsonl` reads REAL judge dict via `.get()` (endpoint never worked: every row → `{"error"}` with HTTP 200); attribute fallback only for legacy shapes | `8fc3560` | `tests/T03_capability/test_flow_11_admin_import_scp_standard.py::test_import_jsonl_reads_real_judge_dict_contract` (TMX-NEW; the pre-existing `test_import_jsonl_endpoint_works` only exercises the legacy attribute branch via MagicMock, so the production dict branch was unpinned) | TMX |

### M12 — Background WHY (`85fc67f`, `f26324a`, `07b6358`, `fa9da62`, `3a36b32`, `4f451df`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 22 | PF-1: `init_why_db` logger defined — WhyEngine() instantiable on fresh DB (duplicate-column handler no longer NameError) | `85fc67f` | `tests/T03_capability/test_flow_12_background_why_scp_standard.py::test_init_why_db_idempotent_and_schema_complete` (TMX-NEW; second deterministic init pass walks the duplicate-column handler) | TMX |
| 23 | PF-1b/D6: `claimed_at` ALTER bare `except:pass` → observable debug log | `85fc67f` | same TMX-NEW test (handler executed, no raise; log-observability aspect structural) | TMX |
| 24 | PF-2: `whyengine` module logger defined — error/info paths no longer NameError inside except | `85fc67f` | `...flow_12...::test_why_engine_verifies_past_decisions` (execute_pending_plans reaches its terminal `logger.info`; pre-fix this raised NameError) | PIN |
| 25 | PF-3: plan status UPDATE by exact `plan_id` (was `UPDATE..ORDER BY..LIMIT 1` → OperationalError → plans stuck `pending` forever) | `85fc67f` | `...flow_12...::test_why_engine_verifies_past_decisions` (asserts `status=='executed' (PF-3 regression)`) | PIN |
| 26 | PF-4a: `get_judge()` wires real WhyEngine onto judge singleton | `85fc67f` | `tests/T01_boot/test_flow_01_boot_background_scp_standard.py::test_get_judge_wires_why_engine_onto_judge_singleton` (TMX-NEW) | TMX |
| 27 | PF-4b: WHY verify loop wired into the ACTIVE lifespan (`api_server_parts/lifespan.py`), thread on `app.state` | `85fc67f` | `...flow_01...::test_lifespan_starts_why_verify_scheduler_thread` (TMX-NEW; asserts live named daemon thread `scp-why-verify-scheduler`) | TMX |
| 28 | PF-5: `SCP_WHY_WIKIPEDIA_BASE` / `SCP_WHY_NASA_BASE` / `SCP_WHY_OPENMETEO_BASE` endpoint seams (config, not mock) | `85fc67f` | `...flow_12...` autouse fixture `m12_offline_env` + `::test_query_wikipedia_returns_results`, `::test_query_nasa_returns_results`, `::test_query_open_meteo_returns_results`, `::test_why_sources_handle_rate_limits` (real local ThreadingHTTPServer round-trips) | PIN |
| 29 | PF-6: `confidence_threshold` column created+migrated (claim `RETURNING` no longer `no such column`) | `f26324a` | `...flow_12...::test_init_why_db_idempotent_and_schema_complete` (TMX-NEW, PRAGMA assert) + `::test_why_engine_verifies_past_decisions` (claim+execute works) | TMX+PIN |
| 30 | PF-7: open-meteo target percent-encoded (multi-word target was ValueError → silent None) | `f26324a` | `...flow_12...::test_query_open_meteo_encodes_multi_word_target` (TMX-NEW; pre-existing SRC-3 tests only used single-word targets) | TMX |
| 31 | PF-8: `VerificationPlan` resolved lazily in whyengine (direct-import order no longer NameError → `executed: 0` forever) | `07b6358` | `...flow_12...` imports `whyengine` DIRECTLY (line 68) then `::test_why_engine_verifies_past_decisions` runs create+execute through that order | PIN |
| 32 | D6: failed claim-release logged at WARNING (was bare `except:pass`, row claimed forever with no trace) | `fa9da62` | `...flow_12...::test_claim_release_failure_is_logged_not_swallowed` (TMX-NEW; seam fault injection + caplog + row-stays-claimed postcondition) | TMX |
| 33 | Empty/whitespace evidence must not verify as PASS (single source) — DNA #22 | `3a36b32` | `...flow_12...::test_why_engine_empty_evidence_is_not_a_pass` | PIN |
| 34 | Multi-source empty evidence must not PASS; real non-empty match still PASSes (no over-tighten) | `4f451df` | `...flow_12...::test_why_engine_multisource_real_match_still_passes` (+ empty-evidence leg re-asserted in `::test_why_engine_verifies_past_decisions`) | PIN |

### M13 — Data sources & Learning (`76b7624`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 35 | `/v104/learn/consolidate` calls real `KnowledgeConsolidator.consolidate()` with honest `ok_stub_noop`/`minimal_stub_passthrough` contract (was nonexistent `consolidate_unverified()` → 500 every call) | `76b7624` | `tests/T03_capability/test_flow_13_free_api_learning_scp_standard.py::test_v104_learn_consolidate_stub_contract` | PIN |

### M14 — v106 Audit/Self-model (`cf34778`)

| # | Fix (contract) | Commit | Pinning test | Status |
|---|---|---|---|---|
| 36 | `/v106/audit/reports` + `/v106/capabilities/{cap_id}` require admin auth (was unauthenticated read of internal audit/capability data) | `cf34778` | `tests/T03_capability/test_flow_17_self_model_capability_scp_standard.py::test_v106_audit_reports_requires_admin`, `::test_v106_capabilities_requires_admin` | PIN |

## Non-product commits in range (excluded from matrix, with reason)

| Commit | Kind | Reason |
|---|---|---|
| `e05c885` fix(T00): mutation tests use system temp | harness | Test-infra fix; pinned by its own file `tests/T00_integrity/test_test_infrastructure_fail_closed.py` (the mutation tests ARE the pin). |
| `b816f63`, `7ebb732`, `96f0280`, `d8c084f`, `c03402f`, `b713aa8`, `fe6d27b`, `c96f8a6`, `2cc7ed6`, `fd3f742`, `839f0f4`, `c06b223`, `8fcb086`, `37c9d87`, `8f4bf00`, `481ac07` | chore(test) | L3 de-shape / test hygiene only — no product behavior. |
| `5f8fa88`, `05c7b01`, `6cdb424`, `0358578`, `0c2211c` | fix(Mx)/docs closure records | Closure JSON + evidence artifacts (records, not behavior). |
| `c5a6838`, `ee5d038`, `e164e81`, `514f1c9`, `c9955e1`, `833bc9e`, `872067a`(runbook parts), `9c7f186`, `d5cf798`, `4f451df`(report leg) | docs | Docs/runbooks/flow-map/header — per task: no test needed. |

## Result

- Product fix rows: 36 (35 in-range fix contracts + 1 M02 pre-range row)
- PINNED by pre-existing tests: 27 rows
- MISSING → patched by TMX this session: 8 rows via 7 new tests (rows 17, 21, 22, 23, 26, 27, 30, 32 — rows 22+23 share one test; row 29/PF-6 is TMX+PIN: existing execution pin plus the new schema leg)
- Un-pinnable: 0 (every product fix in range carries a behavioral pin)

### New tests added (file::test)

1. `tests/T03_capability/test_flow_11_admin_import_scp_standard.py::TestFlow11AdminImport::test_import_jsonl_reads_real_judge_dict_contract`
2. `tests/T03_capability/test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_save_prediction_persists_entity_column`
3. `tests/T03_capability/test_flow_12_background_why_scp_standard.py::TestFlow12BackgroundWhy::test_init_why_db_idempotent_and_schema_complete`
4. `tests/T03_capability/test_flow_12_background_why_scp_standard.py::TestFlow12BackgroundWhy::test_claim_release_failure_is_logged_not_swallowed`
5. `tests/T03_capability/test_flow_12_background_why_scp_standard.py::TestFlow12BackgroundWhy::test_query_open_meteo_encodes_multi_word_target`
6. `tests/T01_boot/test_flow_01_boot_background_scp_standard.py::TestFlow01BootBackground::test_lifespan_starts_why_verify_scheduler_thread`
7. `tests/T01_boot/test_flow_01_boot_background_scp_standard.py::TestFlow01BootBackground::test_get_judge_wires_why_engine_onto_judge_singleton`

All 7 are no-mock on product logic: real DB (`db_manager`), real HTTP fixtures via config seams, real lifespan boot; the only injected faults are documented seam injections (judge stub shape in M11 = the real dict contract shape; db_exec/execute_plan failure injection for the D6 release path), mirroring the ERR-1 failure-branch pattern already used by flow_03.

### Pytest evidence (T03 + T02 + T00 + T01, `-q`)

| Run | Result | Exit |
|---|---|---|
| Baseline BEFORE adding tests @ `c9955e1` | 4 failed / 944 passed (pre-existing: flow_07 auto_rollback, flow_08 audit_stats/findings requires_admin, test_hands_authority_pep bridge denial) | 1 |
| 7 new tests, isolated | 7 passed | 0 |
| 4 touched files, full | 118 passed | 0 |
| Full regression AFTER | 3 failed / 952 passed — the 3 failures are byte-identical to baseline (flow_08 x2 + test_hands_authority_pep); the baseline flow_07 auto_rollback failure did NOT reproduce in the after-run (flaky, no product or test change touches flow_07). Fail count did not increase: 4 → 3. | 1 |

PASS_WITHIN_SCOPE: green here means "no failure observed in these 4 directories at this commit on this machine"; it does not claim repo-wide greenness nor production readiness (the 4 pre-existing failures above are outside TMX scope and left untouched, per mandate "fail không tăng").

## Open questions / limits (DNA #23)

- Row 23 (PF-1b debug-log observability) is pinned behaviorally for the no-crash leg; the mere presence of the debug line is structural, not asserted (log-content assertion on a debug idempotency path was judged over-tightening).
- `test_import_jsonl_endpoint_works` (pre-existing) still exercises the legacy attribute fallback branch; the production dict branch is now pinned separately (row 21). The fallback itself is product contract and remains pinned.
- PF-4b pin asserts scheduler START (thread alive); the 180s warm-up + 5min cadence loop body is not exercised in unit time — that belongs to runtime probes (M12 D3 evidence).
