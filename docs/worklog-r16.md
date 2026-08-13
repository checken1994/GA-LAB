# SCP R15 — 15-Question Structured Audit · Worklog (R16)

> Task: Run a 15-question structured audit on SCP R15 codebase, following the user's
> rigorous framework (codebase analysis → code → SCP claims → test → dependencies →
> devil's advocate → top 10). Then compare with previous deep-research-report.md.
> Previous artifacts available:
> - Codebase: /tmp/scp-r15-extract/scp-dna-audit-round11-full/scp/ (383 .py, ~119K LOC)
> - Lint results: /home/z/my-project/scp-r15-lint-results/ (6 tools, 36,943 raw findings)
> - Lint tools: /tmp/scp-lint-venv/bin/{ruff,pyflakes,pylint,vulture,mypy,bandit}
> - Previous report: /home/z/my-project/deep-research-report.md (705 lines)

---
Task ID: 1
Agent: Main (orchestrator)
Task: Phase 1 — Verify previous artifacts, set up worklog for 15-question audit.

Work Log:
- Verified /home/z/my-project/upload/scp-r15-final.zip exists (2.4MB)
- Verified previous extraction at /tmp/scp-r15-extract/scp-dna-audit-round11-full/scp/ (383 .py files)
- Verified previous lint results at /home/z/my-project/scp-r15-lint-results/ (13 files: AGGREGATED_FINDINGS.md, MANUAL_LOGIC_FINDINGS.md, MANUAL_DEADCODE_FINDINGS.md, ruff.json, pyflakes.txt, pylint.txt, vulture.txt, mypy.txt, bandit.json, etc.)
- Verified lint tools at /tmp/scp-lint-venv/bin/ (ruff 0.16.2, pyflakes 3.4.0, pylint 4.0.7, vulture 2.16, mypy 2.3.0, bandit 1.9.4)
- Verified previous report at /home/z/my-project/deep-research-report.md (705 lines, 13 sections)
- Created this worklog (worklog-r16.md) to track 15-question audit separately from previous worklog.md

Stage Summary:
- All previous artifacts available for reuse — subagents should LEVERAGE existing lint data, not re-run tools
- 15 questions grouped into 4 parallel subagent tasks (2-a, 2-b, 2-c, 2-d) + Main does Q15 + Q16
- Previous report was TOOL-DRIVEN (6 tools → 3 buckets); this audit is QUESTION-DRIVEN (15 structured questions)
- Key NEW areas not in previous report: state machine (Q8), false confidence (Q11), test quality (Q12-13), dependency audit (Q14), devil's advocate (Q15), enforcement tracing (Q10)

---
Task ID: 2-d
Agent: Subagent D (test quality + false PASS detection)
Task: Q12 (test quality audit) + Q13 (false PASS detection) for SCP R15 codebase.

Work Log:
- Read worklog-r16.md (Task 1 setup) + worklog.md (Subagent A/B/C context) — confirmed codebase at /tmp/scp-r15-extract/scp-dna-audit-round11-full/scp/ (383 .py, ~119K LOC), 6 lint tools, 3 prior findings files.
- Globbed the entire extract for test files: `test_*.py`, `*_test.py`, `tests/**/*.py`, `conftest.py`, `pytest.ini`. Found only 5 .py test files (4 real + 1 shadow canary).
- Counted test functions: 26 total (5 in test_none_safety.py + 4 in test_security.py + 7 in test_cascade.py + 10 in test_judge_characterization.py). Parametrize/hypothesis expansion: ~3,025 test cases.
- Identified framework: pytest (primary) + hypothesis (property-based, gated by skipif). NO async tests despite `asyncio_mode=auto` in pyproject.toml. NO coverage config (pytest-cov declared but no .coveragerc, no threshold).
- Read all 5 test files in full + conftest.py + pyproject.toml + requirements-dev.txt to understand test design.
- Cross-referenced critical SCP paths against test suite: grep `verify_chain|UnderstandingChecker|rank_fixes|run_reality_test|check_pending_permissions|policy_gate|confidence_ranker|why_gate|reality_test|understanding_check` across scp/tests/ → 0 hits. ZERO tests reference any R12-R15 autofix feature.
- Classified all 26 tests into 6 categories: BEHAVIOR (genuine) 6, BEHAVIOR (partial/flaky) 6, WEAK ASSERTION 5, TAUTOLOGICAL 5, DISABLED/CONDITIONAL 3, FALSE PASS (CRITICAL) 1, SMOKE 1.
- Mental mutation testing on 25 mutations across 15 critical tests. Verified empirically (Python regex reproduction) that BOTH `test_no_dev_mode_bypass_via_grep` (test_cascade.py:108) AND `test_verify_admin_no_dev_mode_bypass` (test_security.py:101) have BROKEN regexes that NEVER match the canonical V104.22 #3 admin auth bypass.
  - test_cascade.py:108 uses `[^\\n]` (literal backslash-n char class) instead of `[^\n]` (newline). Pattern finds 0 matches on any input.
  - test_security.py:101 uses `[^"\n]*"1"` which cannot cross the `"0"` between `SCP_DEV_MODE` and `"1"` in `os.environ.get("SCP_DEV_MODE", "0") == "1"`. Pattern finds 0 matches on canonical bypass.
- Identified 10 false-PASS tests, 10 untested critical production paths, 12 counterexample tests that should exist.
- Wrote /home/z/my-project/scp-r15-lint-results/Q12_Q13_FINDINGS.md (~17 KB, 4 sections: overview, Q12 classification, Q13 mutation testing, recommendations).

Key findings:
- Test suite is EXTREMELY small for a 383-file / 119K LOC codebase: 26 tests, ~882 LOC of test code (1:135 test-to-code ratio vs industry 1:1 to 1:3).
- 38% of tests (10/26) can FALSE-PASS — either via tautological local mirrors (5 tests in test_none_safety.py), env-conditional skips (3 tests), or broken regex (2 tests).
- The single MOST DANGEROUS false-PASS: `test_no_dev_mode_bypass_via_grep` (test_cascade.py:108). Its regex uses `[^\\n]` (literal backslash-n char class) and `\\n` (literal string) — never matches real newlines. Verified empirically: pattern finds 0 matches even on the exact bypass code it claims to catch. The DUPLICATE check in test_security.py:101 is ALSO broken. The V104.22 #3 admin auth bypass could be re-added verbatim and BOTH tests would still pass.
- The single MOST CRITICAL UNTESTED PATH: `ImmutableAuditLog.verify_chain` (policy_gate.py:420). Subject of 3 prior audit rounds (R12-3 fixed "computed hash but never compared", R13 verified "callable" not "called", R14/R15 found dead). ZERO tests for either correctness (does it detect tampering?) or wiring (does autofix actually call it?). Recursive PASS≠TRUE (DNA #22) — the audit log itself has the bug it was supposed to catch.
- The entire R12-R15 autofix V3/V4 manifest — policy_gate, confidence_ranker, reality_test, why_gate, understanding_check — has ZERO test coverage. Not even a smoke test. Every claimed feature in V3_MANIFEST.md and V4_MANIFEST.md is test-free.

Most surprising finding: The R12-3 historical bug (verify_chain computed hash but didn't compare it) was "tested" only as docstring examples in SCP_DNA_AUDIT_ROUND12.md:79-80 — never as actual pytest code. The recursive PASS≠TRUE pattern (DNA #22) applies to the audit itself: the audit documented the test, didn't write it. R14/R15 trusted R13's "callable" verification and didn't notice the test was never written.

Stage Summary:
- Total test files surveyed: 5 (4 real + 1 canary)
- Total test functions: 26 (~3,025 cases after expansion)
- Tests providing genuine protection: 6/26 (23%)
- Tests that can false-PASS: 10/26 (38%)
- Critical production paths with zero test coverage: 10
- Mental mutations where test failed to catch bug: 10/25 (40%)
- Counterexample tests that should exist: 12
- Output: /home/z/my-project/scp-r15-lint-results/Q12_Q13_FINDINGS.md
- Most dangerous false-PASS: test_no_dev_mode_bypass_via_grep (test_cascade.py:108) — regex broken at escape level, never matches
- Most critical untested path: verify_chain (policy_gate.py:420) — tamper-evidence gate, 3 audit rounds, zero tests

---
Task ID: 2-a
Agent: Subagent A (Q0 + Q1 + Q8 — codebase analysis, runtime reachability, state machine reconstruction)
Task: Foundational/architectural questions — analyze the SCP R15 codebase from scratch (no doc trust), build runtime call graph from production entrypoints, reconstruct all state machines, find INVALID/MISSING/STUCK transitions.

Work Log:
- Read worklog-r16.md (Task 1 setup) + worklog.md (previous audit context: 3 subagents A/B/C, 36,943 raw lint findings, 28 manual dead-code findings G1-G6, 20 manual logic findings L1-L7, deep-research-report.md at 705 lines).
- Verified codebase at /tmp/scp-r15-extract/scp-dna-audit-round11-full/scp/ (348 .py files excluding __init__, ~119K LOC, 19 top-level subdirs).
- Q0 (Codebase analysis from scratch):
  * Grep for `if __name__ == "__main__"` → 12 hits (4 production entrypoints + 8 smoke tests).
  * Grep for `app = FastAPI(` → 1 hit at api_server.py:427. Grep for `uvicorn.run` → 2 hits (__main__.py:87, api_server.py:1234).
  * Grep for `argparse.ArgumentParser` → 11 hits (autofix/runner, benchmark, experience, prediction, 7 meta/* CLIs).
  * Read api_server.py (1241 lines), __main__.py (99 lines), autofix/runner.py (636 lines) to trace execution flow.
  * Read api_server_parts/helpers.py:get_judge (line 372) — singleton with double-checked locking.
  * Read runtime/judge.py + judge_parts/judgecore_mixin.py (3248 lines, 28 phases documented at line 96-147).
  * Built dependency graph via `grep -rh "^from scp\." | sort | uniq -c | sort -rn` — top kernel: scp.interfaces.data_source (63 importers), scp.autofix.classifier (30), scp.core.db_manager (24), scp.runtime.slm_base (16).
  * Identified circular deps: judge.py ↔ judge_parts/* (broken by types.py extraction Task 19-A); api_server.py ↔ api/routes/* (broken by api/_shared.py PEP 562 __getattr__).
- Q1 (Runtime reachability via call graph):
  * BFS from FastAPI entrypoint (E1+E2): traced 4-level deep call chains for /ask hot path, lifespan startup, autofix CLI, benchmark CLI.
  * Cross-referenced 16 dead-code findings (G2-1..G2-16) from MANUAL_DEADCODE_FINDINGS.md — all 16 confirmed.
  * NEW unreachable finding: scp/foundation/{parser,batch}.py + scp/consolidator/consolidator.py + scp/runtime/engine.py:SCPV14 class + scp/runtime/engine_parts/scpv14_process_mixin.py + scp/runtime/healing_v14.py:V14SelfHealingEngine + scp/api/_lifespan.py — ALL unreachable from FastAPI entrypoint (only reachable via runtime/engine.py:SCPV14 which is never instantiated).
  * CRITICAL NEW finding: SCPV14 class is NEVER instantiated in production (grep "SCPV14(" returns 3 hits, all in docstrings). This means DirectAPIVerifier (instantiated only at engine.py:132 inside SCPV14.__init__) is NEVER created → judgecore_mixin.py:1496 `if self.v13.direct_verifier:` is ALWAYS False → Step 7 "Reality check DirectAPIVerifier fallback" is DEAD CODE in production despite being documented as wired.
  * Refined G2-1: previous audit said "entire 503-LOC intent_inference_engine module is dead" — INCORRECT. The MODULE is reachable (via bug_report_validator.py:162 → runner_phases/report.py:132 → runner.py → lifespan). Only the standalone `infer_intent()` function at module level (line 503) is dead. Recoverable LOC is ~30, not 503.
- Q8 (State machine reconstruction):
  * Grep for `class.*Enum\)|class.*IntEnum|class.*StrEnum` → 13 enum-based state machines.
  * Grep for `status TEXT DEFAULT` in SQL CREATE TABLE → 4 DB-schema state machines.
  * Total: 17 state machines identified.
  * Reconstructed in detail (7 state machines with full transition tables):
    1. WHY Gate (3 states: ALLOW/UPHOLD/REJECT) — R14-KB1 fix confirmed (UPHOLD now reachable via _check_necessity returning False on no-match at why_gate.py:328).
    2. Bug Tier (4 states: TIER_1..4) — classification, not transition.
    3. Governance Action (3 states: UPHOLD/KILL/ESCALATE) — decision matrix at governance_v97.py:69-76.
    4. Falsification Status (8 states) — translation table at falsification_engine.py:217.
    5. SCPMeta Council (4 enums × 3-4 values = 13 states) — voting at scp_meta.py:47-72.
    6. JudgeVerdict.verdict (5 declared, 7 actual: +SPECULATIVE +FLAGGED) — INVALID transitions found.
    7. Prediction status (3 states: pending/verified_correct/verified_wrong) — NO expired state (user's question mentioned EXPIRED but it doesn't exist).
    8. Source reputation status (3 states: active/watchlist/blocked) — STUCK: blocked has no auto-recovery.
    9. Permission request status (5 states: pending/approved/denied/expired/unknown) — STUCK: pending if human doesn't act.
    10. WHY verification plan status (1 state: pending only) — CRITICAL STUCK: status column declared but never updated; execute_pending_plans() has 0 production callers (L1-3 confirmed).
    11. PolicyDecision.severity (3 states: ALLOW/REVIEW/BLOCK) — verify_chain() never called (G2-2 confirmed).
  * Found 5 INVALID transitions (INV-1..INV-5), 8 MISSING transitions (MISS-1..MISS-8), 6 STUCK states (STUCK-1..STUCK-6).
- Wrote Q0_Q1_Q8_FINDINGS.md (~750 lines) at /home/z/my-project/scp-r15-lint-results/Q0_Q1_Q8_FINDINGS.md with 8 sections: production entrypoints, execution flow chains, module boundaries + dep graph, data flow, PROVEN vs INFERRED table, reachable/unreachable modules, side effects, state machines (overview + 11 detailed reconstructions + INVALID/MISSING/STUCK tables).

Most surprising architectural discovery:
- runtime/engine.py:SCPV14 — the documented "ENTRY POINT" of V14 architecture (per its own docstring: "SCPV14 Gateway / SCPV14 entry point") — is NEVER INSTANTIATED in production. All 3 SCPV14() references are in docstrings. The actual production entrypoint is runtime/judge.py:RealityJudge, which creates its own SCPV13 (from core/scp_v14.py) directly at judge.py:135, bypassing runtime/engine.py:SCPV14 entirely. This means:
  * DirectAPIVerifier (instantiated only at engine.py:132 inside SCPV14.__init__) is NEVER created.
  * self.v13.direct_verifier is ALWAYS None in production RealityJudge.
  * judgecore_mixin.py:1496 `if self.v13.direct_verifier:` is ALWAYS False → Step 7 "Reality check DirectAPIVerifier fallback" is DEAD CODE in production.
  * foundation/{parser,batch}.py + consolidator/consolidator.py (only lazy-imported by SCPV14.__init__) are UNREACHABLE in production.
- This is the same recursive PASS ≠ TRUE pattern (DNA #22) the previous audit found in R13's reality test: SCPV14 passes ast.parse + import-graph checks (PASS) but is never actually instantiated (not TRUE). Documentation describes an intended design; runtime executes a different one.

Stage Summary:
- Production entrypoints: 4 (E1 python -m scp, E2 FastAPI app, E3 autofix CLI, E4 benchmark CLI) + 12 non-production __main__ smoke tests
- Reachable modules from FastAPI entrypoint: ~335 of 348 .py files
- UNREACHABLE modules from FastAPI entrypoint: ~13 (4 capabilities + 3 foundation/consolidator/engine_parts + 3 runtime/engine+parts + 1 api/_lifespan + 1 benchmark + 1 historical)
- State machines found: 17 (13 enum + 4 DB-schema)
- State machines reconstructed in detail: 11 (WHY Gate, Bug Tier, Governance, Falsification, SCPMeta, JudgeVerdict, Prediction, Source Reputation, Permission, WHY Plan, PolicyDecision)
- INVALID transitions: 5 (verdict FLAGGED/SPECULATIVE not in enum; KILL docstring drift; dead sentinel var; missing EXPIRED state)
- MISSING transitions: 8 (WHY plan status never updated; no prediction EXPIRED; no blocked→active auto-recovery; engine never auto-polls permissions; verify_chain never called; etc.)
- STUCK states: 6 (WHY plan pending forever; prediction pending if fetch fails; source blocked terminal; permission pending if human doesn't act; verdict FAIL/CONFLICT/SPECULATIVE/FLAGGED terminal; PolicyDecision BLOCK terminal)
- Most critical finding: SCPV14 class never instantiated → DirectAPIVerifier dead in production → Step 7 reality check fallback is dead code. NEW finding not in previous audit.
- Most critical state machine: WHY verification plan — 1 state, 0 transitions, status column declared but never used. Plans accumulate forever. (L1-3 fully confirmed via state-machine analysis.)
- Output: /home/z/my-project/scp-r15-lint-results/Q0_Q1_Q8_FINDINGS.md
- Constraints honored: READ-ONLY (no SCP source modified), no tests written, SCP engine not run, reused existing lint data (MANUAL_DEADCODE_FINDINGS.md, MANUAL_LOGIC_FINDINGS.md, AGGREGATED_FINDINGS.md).

---
Task ID: 2-c
Agent: Subagent C (manual SCP-critical audit)
Task: Q5 (contracts) + Q6 (logic invariants) + Q7 (edge cases) + Q9 (arch vs impl) + Q10 (enforcement tracing) + Q11 (false confidence paths). These are the SCP-specific killer questions — SCP is an anti-hallucination system, so any path that returns CONFIDENT/PASS without evidence is worse than 100 dead functions.

Work Log:
- Read worklog.md + worklog-r16.md + MANUAL_LOGIC_FINDINGS.md (Subagent B's 20 findings) as seed.
- Read 33 files across SCP codebase: constitution.py, why_gate.py, why_engine.py, why_execute_plan.py, understanding_check.py, governance_v97.py, confidence_ranker.py, policy_gate.py, permission.py, engine.py, evidence_replay.py, bug_report_validator.py, intent_inference_engine.py, realtime_verifier.py, reality_test.py, post_fix_verify.py, judge.py, judge_parts/types.py, judge_parts/judgecore_mixin.py (3247 LOC — partial), source_reputation.py, source_watchlist.py, react_agent.py, v105_routes.py, api_server.py, verdict_predictor.py, R12/R13/R14/R15 audit reports, V4_MANIFEST.
- Ran 30+ Grep searches to verify caller/callee wiring across 383 .py files.
- For each Q5 contract: documented caller (file:line), callee (file:line), expected vs actual return, nullable/error-state, mismatch impact.
- For each Q6 invariant: documented invariant, precondition, postcondition, violation path (file:line).
- For each Q7 edge case: 12 categories × 2-3 examples each with file:line.
- For each Q9 arch-vs-impl: 4 categories (NOT_EXISTS / NOT_USED / NOT_ENFORCED / DIFFERS).
- For each Q10 invariant: full chain invariant → enforcement code → caller → runtime path → status (ENFORCED / PARTIAL / PROMPT_ONLY / METADATA_ONLY / DOCUMENTED_ONLY).
- For each Q11 false-confidence path: the CONFIDENT return location (file:line), upstream failure mode, trigger condition, impact, and bypassed safety layers.

Key findings:
- **3 CRITICAL false-confidence paths** (Q11):
  - Q11-FP-1: `judge_with_react_fallback` (judge.py:1033) — ReActAgent's `_score_observation` (length+digits heuristic) upgrades UNKNOWN→PASS. Raw LLM answer of ≥200 chars with a digit becomes confidence 0.9 PASS, bypassing WHY gate, antibodies, watchlist, source reputation. **THE SCP KILLER BUG** — Model > Reality, exact opposite of DNA #26.
  - Q11-FP-2: `why_execute_plan.execute_plan` (why_execute_plan.py:79-82) — returns PASS/0.95 for `evidence_type` in deterministic set WITHOUT querying any source. Evidence_type is set by regex-matching question text.
  - Q11-FP-3: `judgecore_mixin.py:1011-1038` — Deterministic SLM short-circuit returns PASS/0.95 with NO adversary, NO WHY gate, NO antibodies, NO governance. A bug in MathSLM/ConversionSLM/StatisticsSLM/LogicSLM is unchecked.
- **1 CRITICAL enforcement gap** (Q10-8): Governance KILL is enforced inside `judge_async`, but `judge_with_react_fallback` mutates verdict.verdict AFTER (judge.py:1033) — overriding ESCALATE→PASS. ESCALATE is silently bypassed.
- **18 NOT-ENFORCED invariants** (Q10): 6 ENFORCED, 11 PARTIAL, 0 PROMPT_ONLY, 0 METADATA_ONLY, 4 DOCUMENTED_ONLY, 1 CRITICAL-BYPASS. verify_chain (Q10-4, Q10-10), check_pending_permissions (Q10-5), is_in_kev (Q10-18) remain dead (confirmed L1-4 still alive in R15).
- **14 contract mismatches** (Q5) — including 5 CRITICAL: Q5-1 (ReActAgent confidence), Q5-2 (execute_plan PASS without source), Q5-3 (reality_test_ok tri-state), Q5-4 (ingestion_decision fail-open 1.0), Q5-5 (verify_patch_realtime ok=True on crash).
- **12 invariant violations** (Q6) — 4 CRITICAL across confidence_ranker, why_execute_plan, react_agent, policy_gate.
- **27 edge case gaps** (Q7) — 12 categories × ~2-3 each. 6 CRITICAL including the timeout-as-failure (Q7-4.3+Q5-8) and DB-write-failure-silent (Q7-10.1, Q7-10.2).
- **13 arch-vs-impl discrepancies** (Q9) — 4 categories. Most important: Q9-C1 (WHY gate UPHOLD advisory for verdicts), Q9-C3 (Governance KILL bypassed by ReActAgent wrapper), Q9-D2 (No Hallucination principle violated by ReActAgent path).

Most surprising finding: Q11-FP-1. R12-R15 audits PASSED (all 36,943 lint findings green, all R13 reality tests green) but the ReActAgent false-confidence path was TRUE (alive) — the audit had the bug it was supposed to catch (DNA #22 recursive). The path is reachable from production `/ask` endpoint with NO env vars required. SCP's tagline is "Reality > Model" (DNA #26) — this path is "Model > Reality", the exact failure mode SCP was designed to prevent.

Most common root cause pattern: "Bool return type can't represent tri-state (pass/fail/unknown)" — appears in 9 of the findings (Q5-3, Q5-9, Q5-11, Q6-1, Q6-6, Q11-FP-5, Q11-FP-7, Q11-FP-8, Q11-FP-9). Designers use True/False as default when correct answer is "unknown".

Output: /home/z/my-project/scp-r15-lint-results/Q5_Q6_Q7_Q9_Q10_Q11_FINDINGS.md (1104 lines, ~50KB)

Stage Summary:
- Q5 contract mismatches: 14 (5 CRITICAL)
- Q6 invariant violations: 12 (4 CRITICAL)
- Q7 edge case gaps: 27 (6 CRITICAL, across 12 categories)
- Q9 arch vs impl discrepancies: 13 (4 categories: 2 NOT_EXISTS, 13 NOT_USED, 6 NOT_ENFORCED, 4 DIFFERS — overlap with Q2 dead code)
- Q10 invariants: 6 ENFORCED · 11 PARTIAL · 0 PROMPT_ONLY · 0 METADATA_ONLY · 4 DOCUMENTED_ONLY · 1 CRITICAL-BYPASS (Q10-8 Governance KILL bypassed by ReActAgent wrapper)
- Q11 false confidence paths: 9 (3 CRITICAL, 4 HIGH, 2 MEDIUM)
- Single most dangerous false-confidence path: Q11-FP-1 — `judge_with_react_fallback` → `ReActAgent.solve` → `_score_observation` (length+digits heuristic) → `verdict.verdict = "PASS"` at judge.py:1033. SCP returns VERIFIED on raw LLM output.
- DNA #22 (PASS ≠ TRUE) recursive: R12-R15 audits PASSED but Q11-FP-1 was TRUE (alive). The audit had the bug it was supposed to catch.
- DNA #26 (Reality > Model): Q11-FP-1 is the inversion — Model > Reality. ReActAgent's LLM answer length determines confidence, not any external reality check.
- DONE. Reality giữ quyền trả lời cuối cùng. (DNA #26 🌍)

---
Task ID: 2-b
Agent: Subagent B (code-quality audit)
Task: Q2 (dead code 7-way classification) + Q3 (duplicate code) + Q4 (error handling impact) + Q14 (dependency audit) for the 15-question structured audit.

Work Log:
- Read worklog-r16.md + worklog.md for context (15-question audit, 4 parallel subagent tasks).
- Read MANUAL_DEADCODE_FINDINGS.md (28 findings, 3-way classification) + AGGREGATED_FINDINGS.md (38984-line _cross_tool.json with 1,804 cross-tool locations).
- Sampled 60 of vulture's 531 findings (all 16 high-confidence + 44 from 60% confidence). For EACH, read the source to classify — vulture can't distinguish "fallback" from "dead" or "FastAPI route" from "unused function".
- Classified into 7 categories per user spec:
  * Confirmed dead: 14 (e.g. infer_intent, verify_chain, APICache, SelfHealingEngine dead-duplicate)
  * Potentially dead (vulture FP — dynamic dispatch): 26 (FastAPI routes, ABC contract methods, PEP 562 __getattr__)
  * Compatibility code: 4 (*Expert aliases, real_learning_engine G3-merge stub)
  * Test-only: 2 (reset_why_gate, reset_policy_gate — "for tests" but no test calls)
  * Fallback code (intentional, NOT dead): 6 (SQLite ALTER idempotency, degraded-mode router wiring)
  * Experimental code (WIP, has TODO): 5 (external_trust register_file/verify_all_baselines, ScannerEvolver)
  * Production code: 3 (spot-checks to confirm vulture FPs)
- Found 10 duplicate clusters (up from 1 in previous audit). Top 5 HIGH divergence risk:
  * D1: 4 audit-log writers with different schemas (engine, evolution, ast_scan)
  * D2: 2 self-healing engines (core/healing_engine.py dead, runtime/healing_v14.py live) — same purpose, completely different contracts
  * D4: CircuitBreaker naming collision (core/ vs security/) — same class name, different APIs
  * D6: _check_wikipedia (real impl in fast_learning_engine vs STUB returning None in streaming_factcheck)
  * D8: _verify_fix fail-open pattern duplicated across engine.py + fast_learning_engine.py
- For Q4, sampled top 30 critical-path error handlers from _cross_tool.json (filtered to policy_gate/reality_test/why_gate/understanding_check/evidence/judgecore/verify/falsif/heal paths — 213 of 1,804). For EACH, classified pattern (SWALLOW/SILENT_FALLBACK/LOG_CONTINUE/FALSE_SUCCESS/NARROW) + impact (CRITICAL/HIGH/MED/LOW).
- Found 9 FALSE_SUCCESS paths in anti-hallucination controls (FS-1 through FS-9) — error handlers that convert verification crashes into "verified OK" / "PASS" / "not falsified" status.
- Single highest-impact: realtime_verifier.py:334-338 — `result.ok = True` on verifier crash. Runs before EVERY autofix patch commit.
- For Q14, read requirements.txt + requirements-dev.txt + pyproject.toml. Cross-referenced with grep for actual imports. Found 10 issues:
  * CRITICAL: hypothesis missing from requirements-dev.txt (used in tests/property + scanners)
  * HIGH: target-version="py39" but code uses PEP 604 union types (str | None) on pydantic models — requires 3.10+
  * MED: requests + httpx duplicate (consolidate on httpx)
  * MED: asyncio.create_task without strong ref (RUF006) at api_server.py:289, 999
  * MED: 23 ASYNC230/240/210 findings (blocking I/O in async functions)
  * MED: sqlite3.connect without context manager (7 sites in kb_evolve.py)
  * LOW: numpy==2.1.3 unused direct import (transitive only)
  * LOW: 1,799 G004 f-string-in-log findings
  * LOW: Faker, pytest-metadata, pytest-json-report possibly unused
  * LOW: pydantic-settings possibly unused
- Wrote /home/z/my-project/scp-r15-lint-results/Q2_Q3_Q4_Q14_FINDINGS.md (~700 lines, structured per user spec with 7-way table, duplicate clusters table, top-30 error handler table, dependency inventory + issues).

Key findings (top 3 most surprising):
1. **9 FALSE_SUCCESS paths in anti-hallucination controls** — the codebase's "DNA #7 fail-open" principle is MISAPPLIED to verification paths. Realtime verifier, _verify_fix, _verify_learned_fact, hypothesis scanner, understanding_check, falsify_with_llm, vulture cross-file check, import check — all convert crashes into "verified OK". This is the EXACT "false confidence" anti-pattern the user demanded we find.
2. **Vulture FP rate is ~47%** — ~250 of 531 findings are false positives caused by dynamic dispatch patterns (FastAPI @router decorators, ABC @abstractmethod contracts, PEP 562 __getattr__ module hooks). A naive "delete all vulture findings" pass would BREAK the codebase. The 7-way classification is essential.
3. **CircuitBreaker naming collision** (core/ vs security/) — same class name in 2 packages with completely different contracts. Author left a 17-line warning comment but didn't rename. Importer must alias manually.

Root-cause meta-finding:
The codebase has a documented design principle "DNA #7: fail-open for availability" — but it's applied INDISCRIMINATELY to verification paths where fail-closed is the correct behavior. The author conflated "don't crash the server" (correct for runtime) with "don't block the fix" (incorrect for verification). The fix is not just code — it's a design-principle clarification: "DNA #7 fail-open applies to RUNTIME AVAILABILITY, NOT to VERIFICATION INTEGRITY."

Stage Summary:
- Files read: 18 source files (helpers.py, _shared.py, healing_engine.py, healing_v14.py, circuit_breaker.py x2, why_gate.py, why_engine.py, understanding_check.py, policy_gate.py, evidence_replay.py, post_fix_verify.py, realtime_verifier.py, hypothesis_scanner.py, kb_evolve.py, slm_base.py, external_trust.py, scp_meta.py, meta.py) + 4 lint artifacts (vulture.txt, _cross_tool.json, MANUAL_DEADCODE_FINDINGS.md, AGGREGATED_FINDINGS.md) + 2 worklog files + 3 config files (requirements.txt, requirements-dev.txt, pyproject.toml).
- Findings produced: 60 dead-code classifications (7-way) + 10 duplicate clusters + 30 error-handler impact assessments + 10 dependency issues + 9 FALSE_SUCCESS paths in anti-hallucination controls.
- Output: /home/z/my-project/scp-r15-lint-results/Q2_Q3_Q4_Q14_FINDINGS.md (~700 LOC).
- Deliverables per task spec:
  1. Q2 counts: 14 confirmed / 26 potentially dead / 4 compat / 2 test-only / 6 fallback / 5 experimental / 3 production (sampled).
  2. Q3: 10 duplicate clusters; top risk = D4 CircuitBreaker naming collision.
  3. Q4: SWALLOW 6 / SILENT_FALLBACK 9 / LOG_CONTINUE 8 / FALSE_SUCCESS 6 / NARROW 1 (sampled 30 of 1804). 9 FALSE_SUCCESS paths in anti-hallucination controls.
  4. Q14: 10 dependency issues (1 CRITICAL: missing hypothesis; 2 HIGH: py39 version mismatch, requests+httpx dup; 4 MED; 3 LOW).
  5. Path: /home/z/my-project/scp-r15-lint-results/Q2_Q3_Q4_Q14_FINDINGS.md
  6. Highest-impact error handler: autofix/realtime_verifier.py:334-338 (verifier crash → result.ok = True).
  7. Production-failure dependency issue: target-version="py39" but code requires 3.10+ (PEP 604 on pydantic models) — install on 3.9 crashes at import time.
- READ-ONLY audit — no source modified. Leveraged existing lint artifacts (didn't re-run tools).

---
Task ID: 3+4+5
Agent: Main (orchestrator)
Task: Q15 (devil's advocate) + Q16 (top 10) + final report + comparison with previous deep-research-report.md.

Work Log:
- Q15 Devil's advocate: verified 10 top findings via grep + empirical testing.
  * Q11-FP-1 (ReActAgent PASS): confirmed reachable — api_server.py:823-824 calls judge_with_react_fallback. HOLDS.
  * SCPV14 never instantiated: confirmed — meta/meta.py:72 imports from scp.core.scp_v14 (stub), not runtime.engine. HOLDS.
  * verify_chain never called: confirmed — only 1 grep hit (a comment). HOLDS.
  * test regex broken: confirmed empirically — [^\\n] matches 0, [^\n] matches 1. HOLDS.
  * understanding_check return True: confirmed — comment says "accept" but it's same semantic inversion as R14 WhyGate. HOLDS (severity HIGH not CRITICAL).
  * All 10 findings survived devil's advocate. 0 retracted.
- Q16 Top 10: ranked by correctness → data integrity → security → runtime reliability → invariant → maintainability → performance → dead code.
  * #1: judge.py:1033 ReActAgent PASS (correctness+security+invariant) — THE SCP KILLER
  * #2: judgecore_mixin.py:881-928 deterministic SLM short-circuit
  * #3: why_execute_plan.py:79-82 PASS without querying source
  * #4: judge.py:1033 Governance KILL bypassed
  * #5: policy_gate.py:647-671 fail-open on audit-log failure
  * #6-10: verify_chain, check_pending_permissions, understanding_check, test regex, SCPV14 dead
- Wrote deep-research-report-r16.md (final report) with:
  * 15-question findings (aggregated from 4 subagents)
  * Q15 devil's advocate (10/10 held)
  * Q16 top 10 priority ranked
  * Detailed comparison with previous deep-research-report.md
- Copied to /home/z/my-project/download/deep-research-report-r16.md.

Stage Summary:
- Final report: /home/z/my-project/deep-research-report-r16.md + /home/z/my-project/download/deep-research-report-r16.md
- 4 subagent findings files in /home/z/my-project/scp-r15-lint-results/ (Q0_Q1_Q8, Q2_Q3_Q4_Q14, Q5_Q6_Q7_Q9_Q10_Q11, Q12_Q13)
- Key finding: Q11-FP-1 (judge.py:1033 ReActAgent PASS) is THE SCP KILLER BUG — reachable from /ask, returns PASS/conf=0.9 based on LLM answer length+digits, bypasses ALL safety gates. This is the exact failure mode SCP was designed to prevent.
- Comparison: previous report was TOOL-DRIVEN (6 tools → 3 buckets), found verify_chain dead (gate OFF). This report is QUESTION-DRIVEN (15 questions), found false-confidence paths ON (actively returning PASS when shouldn't). The 15-question framework found what tools couldn't.
- DONE. Reality giữ quyền trả lời cuối cùng. (DNA #26 🌍)

---
Task ID: 6
Agent: Main (orchestrator)
Task: User hỏi "phương án sử lý chi tiết" — viết remediation plan chi tiết cho top 10 findings.

Work Log:
- Read actual source code của 10 vị trí bug (judge.py:1025-1045, react_agent.py:185-198, judgecore_mixin.py:1007-1020, why_execute_plan.py:79-86, policy_gate.py:647-671, understanding_check.py:58, test_cascade.py:128-134, engine.py:2294)
- Viết remediation-plan.md với:
  * 4 phase (P0 hotfix → P1 security wiring → P2 tests → P3 cleanup)
  * Per-fix: root cause + before/after code + verification + risk
  * Sequencing + timeline (~2 tuần)
  * Prevention strategy (4 CI gates)
- Copy vào /home/z/my-project/download/remediation-plan.md

Stage Summary:
- File: /home/z/my-project/remediation-plan.md + /home/z/my-project/download/remediation-plan.md
- 10 fixes chi tiết với before/after code
- P0-1 (ReActAgent) là urgent nhất — dừng SCP killer trong 1-2h
- Prevention: 4 CI gates (wiring verification, no false-confidence return, test regex sanity, reality test = called not callable)
- DONE.
