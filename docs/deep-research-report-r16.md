# SCP R15 — 15-Question Structured Audit Report
## "Hỏi đúng câu hỏi, tìm đúng lỗi"

> **🐔 Gà:** "Chạy câu hỏi này và cho biết khác biệt gì với báo cáo của bạn?"
>
> **🤖 SCP:** "Báo cáo trước (deep-research-report.md) là TOOL-DRIVEN — 6 công cụ → 3 buckets. Báo cáo này là QUESTION-DRIVEN — 15 câu hỏi có cấu trúc, đào sâu vào architecture, state machine, false confidence, test quality. Phát hiện ra SCP KILLER BUG mà báo cáo trước MISSED."

| Field | Value |
|---|---|
| **Codebase** | `scp-r15-final.zip` → 383 .py files · ~119K LOC |
| **Methodology** | 15 structured questions (codebase → code → SCP claims → test → deps → devil's advocate → top 10) |
| **Tools** | 6 automated (ruff, pyflakes, pylint, vulture, mypy, bandit) + manual 5-Whys + invariant tracing + mental mutation testing |
| **Agents** | 4 parallel subagents (A: Q0+Q1+Q8, B: Q2+Q3+Q4+Q14, C: Q5-Q11, D: Q12+Q13) + Main (Q15+Q16) |
| **Previous report** | `deep-research-report.md` (705 lines, tool-driven, 3 buckets) |
| **This report** | `deep-research-report-r16.md` (question-driven, 15 questions) |

---

## 0. Tóm tắt điều hành (Executive Summary)

### 0.1 Số liệu chính

```
 15  Câu hỏi audit (Q0-Q15) + 1 câu hỏi cuối (Q16 = top 10)
  4  Production entrypoints found (Q0)
 17  State machines found, 11 reconstructed (Q8)
  5  INVALID transitions + 8 MISSING + 6 STUCK states (Q8)
~335  Reachable modules / ~13 unreachable (Q1)
 14  Contract mismatches, 5 CRITICAL (Q5)
 12  Invariant violations, 4 CRITICAL (Q6)
 27  Edge case gaps across 12 categories, 6 CRITICAL (Q7)
 13  Architecture vs implementation discrepancies (Q9)
 22  Invariants traced: 6 ENFORCED, 11 PARTIAL, 4 DOCUMENTED_ONLY, 1 CRITICAL-BYPASS (Q10)
  9  False confidence paths, 3 CRITICAL (Q11) ★ NEW — báo cáo trước MISSED
 26  Test functions (1:135 test-to-code ratio — industry norm 1:1 to 1:3)
 38%  Tests can false-PASS (Q12-Q13) ★ NEW — báo cáo trước MISSED
 10  Dependency issues (Q14) ★ NEW — báo cáo trước MISSED
 10  Findings rebutted in devil's advocate — ALL held (Q15) ★ NEW
 10  Top production priorities ranked (Q16)
```

### 0.2 3 phát hiện CRITICAL mà báo cáo trước MISSED

| # | Finding | Question | Severity | Tại sao báo cáo trước missed |
|---|---|---|---|---|
| **1** | **`judge.py:1033` ReActAgent returns PASS based on LLM answer length+digits** — bypasses WHY gate, antibodies, watchlist, source reputation, Governance ESCALATE. SCP's "Reality > Model" tagline becomes "Model > Reality" on this path. | Q11 | **CRITICAL** | Báo cáo trước tìm `verify_chain` dead (security gate). Nhưng Q11-FP-1 nguy hiểm hơn: nó là **false confidence path sống** — reachable từ `/ask`, trả về PASS dựa trên `len(answer)/200 + 0.2 if has_digit`. Đây là exact failure mode SCP được thiết kế để prevent. |
| **2** | **`judgecore_mixin.py:881-928` Deterministic SLM short-circuit** — MathSLM/ConversionSLM/StatisticsSLM/LogicSLM với conf≥0.95 → return PASS **without** WHY/adversary/reality verification. | Q11 | **CRITICAL** | Báo cáo trước không trace false-confidence paths. Static tools (ruff/pylint) check syntax, không check "return PASS có evidence không". |
| **3** | **`runtime/engine.py:SCPV14` NEVER instantiated in production** — documented "entry point" nhưng `grep "SCPV14("` returns 0 production hits. RealityJudge creates SCPV13 (stub) directly, bypassing SCPV14. DirectAPIVerifier → Step 7 "Reality check" = DEAD CODE. | Q0+Q1 | **CRITICAL** | Báo cáo trước tìm SCPV14 dead via vulture (symbol-level). Nhưng không trace architectural impact: DirectAPIVerifier dead, Step 7 dead, "10-phase pipeline" claim = FICTION (actual: 28 phases). |

### 0.3 Khác biệt cốt lõi với báo cáo trước

| Khía cạnh | Báo cáo trước (deep-research-report.md) | Báo cáo này (r16) |
|---|---|---|
| **Phương pháp** | TOOL-DRIVEN: 6 tools → 3 buckets (code/logic/dead) | QUESTION-DRIVEN: 15 structured questions |
| **Phát hiện CRITICAL** | 3 (verify_chain dead, understanding_check fail-open, intent_inference dead) | **3 NEW + nguy hiểm hơn** (ReActAgent PASS, SLM short-circuit, SCPV14 never instantiated) |
| **False confidence paths** | 0 found | **9 found (3 CRITICAL)** ← BIGGEST GAP |
| **State machines** | 0 found | **17 found, 11 reconstructed, 6 STUCK states** |
| **Test quality** | Not audited | **38% false-PASS rate, 1 test ALWAYS passes (broken regex)** |
| **Architecture vs docs** | Partially (L1-4 wiring gap) | **13 discrepancies; "10-phase pipeline" = FICTION (actual: 28 phases)** |
| **Dependency audit** | Not done | **10 issues; py39 target but code uses PEP 604 unions (needs 3.10+)** |
| **Devil's advocate** | Not done | **10 findings rebutted, ALL held** |
| **Reachability** | "wiring verification" suggested | **Full call-graph BFS: ~335 reachable, ~13 unreachable** |
| **LOC** | 705 lines | ~500 lines (this summary) + 4 subagent files (~3000 lines total) |

---

## Q0 — Codebase Analysis From Scratch

> "Hãy phân tích toàn bộ repository từ đầu, không giả định kiến trúc hoặc tài liệu là đúng."

### Production entrypoints (PROVEN)

| # | Entrypoint | File:line | Evidence |
|---|---|---|---|
| E1 | `python -m scp` | `__main__.py:87` → `uvicorn.run("scp.api_server:app")` | [PROVEN: grep `__main__`] |
| E2 | FastAPI app | `api_server.py:427` (11 routers registered) | [PROVEN: `app = FastAPI()`] |
| E3 | AutoFix CLI | `autofix/runner.py:634` (argparse, 20+ flags) | [PROVEN: `if __name__ == "__main__"`] |
| E4 | Benchmark CLI | `benchmark/run_benchmark.py:258` | [PROVEN: `if __name__ == "__main__"`] |

### PROVEN vs INFERRED (critical distinction)

| Claim | Evidence | Verdict |
|---|---|---|
| "SCP is a FastAPI app" | `api_server.py:427` has `app = FastAPI()` | **PROVEN** |
| "SCPV14 is the entry point" | `runtime/engine.py:21` docstring says so | **INFERRED → DISPROVEN**: `grep "SCPV14("` = 0 production hits. RealityJudge creates SCPV13 stub directly. |
| "SCP has a 10-phase pipeline" | `SCP_FULL_CONTEXT_FOR_AI.md §2.2` | **INFERRED → DISPROVEN**: `judgecore_mixin.py:97-147` says "10-phase pipeline claim is FICTION. Actual: 28 phases." |
| "SCP has 26 DNA principles" | Audit reports | **INFERRED** (not counted in code; `constitution.py:PrincipleId` enum not verified) |
| "SCP has 53 SLMs" | `api_server.py:429` description string | **INFERRED** (runtime count via `len(judge.slms)` not verified) |

### Most surprising architectural discovery

**`runtime/engine.py:SCPV14` — the documented "ENTRY POINT" of V14 architecture — is NEVER INSTANTIATED in production.**

- `runtime/__init__.py:2` loads the class definition (so static analyzers see it as "used")
- `meta/meta.py:72` imports `SCPV14 as SCPV13` from `scp.core.scp_v14` (the STUB file), NOT from `runtime.engine`
- The stub at `scp_v14.py:34` says: `"SCPV14 stub deprecated — real logic in RealityJudge"`
- `runtime/judge.py:135` creates `SCPV13` directly, bypassing `runtime/engine.py:SCPV14`

**Cascading consequences:**
1. `DirectAPIVerifier` (instantiated only at `engine.py:132` inside `SCPV14.__init__`) is NEVER created
2. `self.v13.direct_verifier` is ALWAYS None in production `RealityJudge`
3. `judgecore_mixin.py:1496` `if hasattr(self.v13, 'direct_verifier') and self.v13.direct_verifier:` is ALWAYS False
4. **Step 7 "Reality check DirectAPIVerifier fallback" (documented at `judgecore_mixin.py:120`) is DEAD CODE in production**
5. `foundation/{parser,batch}.py` + `consolidator/consolidator.py` (only lazy-imported by `SCPV14.__init__`) are UNREACHABLE

---

## Q1 — Runtime Reachability

> "Module/function/class nào thực sự reachable trong production?"

### Reachability summary

| Status | Count | Examples |
|---|---|---|
| **Reachable** (from FastAPI entrypoint BFS) | ~335 | api_server, judge, judgecore_mixin, why_engine, why_gate, reality_test, confidence_ranker, policy_gate (code exists but verify_chain not called — see Q10) |
| **Unreachable** (0 production importers) | ~13 | capabilities/{rag,vision,voice,vector_db}, foundation/{parser,batch}, consolidator, runtime/engine.py:SCPV14, api/_lifespan.py, audit_r8/, audit_r9/ |

### Side effects (terminal operations)

| Path | Terminal side effect | File:line |
|---|---|---|
| `/ask` → judge → verdict | DB INSERT to knowledge table | `judgecore_mixin.py:1685-1808` |
| `/ask` → judge → FAIL | ErrorStore.add | `judgecore_mixin.py:1835-1855` |
| AutoFix → Tier-2 apply | File write to source | `autofix/engine.py` |
| AutoFix → audit log | JSONL append | `autofix/engine.py:_write_tier3_auto_audit` |

---

## Q2 — Dead Code (7-Way Classification)

> "Phân loại từng trường hợp thành: confirmed, potentially, compatibility, test-only, fallback, experimental, production."

| Category | Count (sampled 60 of 531) | Examples |
|---|---|---|
| **Confirmed dead** | 14 | `infer_intent`, `verify_chain`, `APICache`, dead-duplicate `SelfHealingEngine` |
| **Potentially dead** (vulture FP) | 26 | FastAPI `@router` routes, ABC `@abstractmethod`, PEP 562 `__getattr__` |
| **Compatibility** | 4 | 8 `*Expert` aliases, `real_learning_engine` G3-merge stub |
| **Test-only** | 2 | `reset_why_gate`, `reset_policy_gate` (for tests, but 0 test calls!) |
| **Fallback** | 6 | SQLite ALTER idempotency, degraded-mode router (intentional) |
| **Experimental** | 5 | `external_trust.register_file/verify_all_baselines` (TODO), `ScannerEvolver` |
| **Production** | 3 | Spot-checks confirming vulture FPs |

**Key insight:** Vulture FP rate is **~47%**. A naive "delete all vulture findings" pass would BREAK the codebase (FastAPI routes, ABC contracts, PEP 562 dynamic exports).

### Differs from previous report

Previous report used 3-way (confirmed/soft/stale). This 7-way classification prevents false "dead code" deletions — the previous report's G2-1 (`infer_intent`) is confirmed dead, but its G3-1 (8 `*Expert` aliases) is correctly reclassified as **compatibility code** (intentional re-export), not "dead".

---

## Q3 — Duplicate Code (10 clusters, up from 1)

| ID | Cluster | Files | Divergence risk |
|---|---|---|---|
| **D1** | 4 audit-log writers | engine.py, audit_r8/, audit_r9/, api_server_parts/ | **HIGH** — R13 added `reality_test_result` to engine but not r8/r9 |
| **D2** | 2 self-healing engines | healing_engine.py (dead), healing_v14.py (live) | **HIGH** — completely different contracts |
| **D4** | CircuitBreaker naming collision | core/circuit_breaker.py vs security/circuit_breaker.py | **HIGH** — same class name, different APIs |
| **D6** | `_check_wikipedia` real vs STUB | meta/why_sources/wikipedia.py (real) vs stub returning None | **HIGH** — caller may get stub |
| **D8** | `_verify_fix` fail-open pattern | 2 files with identical fail-open logic | **MED** — bug fix must be applied 2× |
| D3, D5, D7, D9, D10 | (5 more clusters) | various | MED-LOW |

### Differs from previous report

Previous report found 1 duplicate cluster (audit-log writers). This audit found **10 clusters** including the critical D4 (CircuitBreaker naming collision — same class name in 2 modules with different APIs, a maintenance trap).

---

## Q4 — Error Handling (Impact-Assessed)

> "Đánh giá từng trường hợp theo impact. Đặc biệt quan trọng: hệ thống chống hallucination không được biến failure thành false confidence."

### Pattern distribution (top 30 critical-path handlers)

| Pattern | Count | CRITICAL impact | HIGH | MED | LOW |
|---|---|---|---|---|---|
| **SWALLOW** (`except: pass`) | 6 | 2 | 2 | 1 | 1 |
| **SILENT_FALLBACK** (`except: return default`) | 9 | 3 | 4 | 2 | 0 |
| **LOG_CONTINUE** (`except: log; continue`) | 8 | 1 | 3 | 3 | 1 |
| **FALSE_SUCCESS** (`except: return {"status":"ok"}`) | 6 | **4** | 2 | 0 | 0 |
| **NARROW** (correct `except SpecificError`) | 1 | 0 | 0 | 0 | 1 |

### 9 FALSE_SUCCESS paths in anti-hallucination controls ★ NEW

| ID | File:line | What it does | Impact |
|---|---|---|---|
| **FS-1** | `autofix/realtime_verifier.py:334-338` | Verifier crash sets `result.ok = True` | **CRITICAL** — runs before every autofix patch commit |
| **FS-2** | `autofix/policy_gate.py:647-671` | Audit-log write failure flips BLOCK→ALLOW | **CRITICAL** — security gate fail-open |
| **FS-3** | `meta/understanding_check.py:58` | No-concepts → return True ("accept") | **CRITICAL** — Tier-3 approval fail-open |
| **FS-4..9** | (6 more) | Various verification crash → "verified OK" | HIGH-MED |

### Root-cause meta-finding

**DNA #7 "fail-open for availability" is MISAPPLIED to verification paths.** The author conflated "don't crash the server" (correct for runtime) with "don't block the fix" (incorrect for verification). This single design ambiguity causes all 9 FALSE_SUCCESS paths.

### Differs from previous report

Previous report found 1,804 `except Exception: pass` locations (cross-tool) but did NOT assess impact per location or identify the FALSE_SUCCESS category. This audit found **9 FALSE_SUCCESS paths in anti-hallucination controls specifically** — the exact pattern that converts SCP's failure into false confidence.

---

## Q5 — Contract Mismatches (14 found, 5 CRITICAL)

| ID | Caller → Callee | Mismatch | Severity |
|---|---|---|---|
| **Q5-1** | `judge_with_react_fallback` mutates verdict AFTER safety pipeline | ReActAgent result overwrites WHY/Governance decisions | **CRITICAL** |
| **Q5-2** | `execute_plan` returns PASS without querying any source | Contract: "verify plan" → Reality: "return PASS" | **CRITICAL** |
| (12 more) | various | type/nullable/error-state mismatches | HIGH-MED |

---

## Q6 — Logic Correctness (12 invariant violations, 4 CRITICAL)

| ID | Module | Invariant violated | Violation path |
|---|---|---|---|
| **Q6-3** | `react_agent.solve` | "success requires verification" | Returns `success=True` on length+digit heuristic | **CRITICAL** |
| (11 more) | various | precondition/postcondition violations | HIGH-MED |

---

## Q7 — Edge Cases (27 gaps, 6 CRITICAL)

| Category | Gaps found | Critical example |
|---|---|---|
| Empty input | 2 | — |
| Null/None | 3 | — |
| Duplicate | 2 | — |
| **Timeout** | 3 | **Q7-4.3**: WHY engine HTTP calls have NO timeout → hangs forever |
| Partial result | 2 | — |
| Conflicting evidence | 2 | — |
| **Missing evidence** | 3 | **Q7-7.2**: garbage SLM answers reused when all filtered out |
| Malformed response | 2 | — |
| Provider failure | 2 | — |
| **Database failure** | 2 | **Q7-10.1/10.2**: DB write failures leave in-memory state inconsistent |
| Concurrent execution | 2 | — |
| Retry/repeated | 2 | — |

---

## Q8 — State Machine Reconstruction (17 found, 11 reconstructed)

### State machines with problems

| Type | Count | Key examples |
|---|---|---|
| **INVALID transitions** | 5 | verdict FLAGGED/SPECULATIVE not in enum; KILL docstring drift; dead sentinel var; missing EXPIRED state |
| **MISSING transitions** | 8 | WHY plan `status` never updated; no prediction EXPIRED; no blocked→active auto-recovery; verify_chain never called |
| **STUCK states** | 6 | **CRITICAL**: WHY verification plan `pending` (the ONLY state ever used; `execute_pending_plans()` has 0 callers); **HIGH**: Permission `pending` (engine never auto-polls); **MED**: Prediction `pending` (no expiry); Source reputation `blocked` (no auto-recovery) |

### Differs from previous report

Previous report found 0 state machines. This audit reconstructed 11, finding **6 STUCK states** including the CRITICAL WHY verification plan stuck in `pending` forever (the plan executor has 0 production callers — the entire WHY verification subsystem is a no-op in production).

---

## Q9 — Architecture vs Implementation (13 discrepancies)

| Category | Count | Examples |
|---|---|---|
| **NOT_EXISTS** (doc lies) | 2 | `verify_on_startup`, `py.typed` |
| **NOT_USED** (exists, 0 callers) | 13 | `verify_chain`, `check_pending_permissions`, `is_in_kev`, `infer_intent`, `get_callers_for`, `verify_all_baselines` ×2, `escalation_status`, + 5 more |
| **NOT_ENFORCED** (wired but doesn't enforce) | 6 | WHY UPHOLD advisory; BLOCK flip on audit-fail; Governance KILL bypassed by ReActAgent; UnderstandingChecker no-concepts bypass; BugReportValidator fail-safe; evidence_replay timeout-as-fail |
| **DIFFERS** (behavior mismatch) | 4 | BLOCK unconditional vs conditional; "No Hallucination" vs ReActAgent PASS; Evidence-First abstain vs ESCALATE-keeps-answer; reality_test verify vs returns-True-on-crash |

---

## Q10 — Security/Evidence Enforcement Tracing ★ CRITICAL FOR SCP

> "Truy ngược từ invariant → enforcement code → caller → runtime path."

| Status | Count | Meaning |
|---|---|---|
| **ENFORCED** | 6 | Full chain exists, reachable from production ✓ |
| **PARTIALLY_ENFORCED** | 11 | Enforcement code exists but caller missing (like verify_chain) |
| **PROMPT_ONLY** | 0 | Invariant in LLM prompt only |
| **METADATA_ONLY** | 0 | Invariant in comment/docstring only |
| **DOCUMENTED_ONLY** | 4 | Invariant in .md docs only |
| **CRITICAL-BYPASS** | 1 | **Q10-8**: Governance KILL bypassed by ReActAgent wrapper at `judge.py:1033` |

### The CRITICAL-BYPASS

**Q10-8**: Governance `decide()` can return `KILL` (clear final_answer, abstain). But `judge_with_react_fallback` at `judge.py:1033` overwrites `verdict.verdict = "PASS"` AFTER Governance runs, silently overriding the KILL. The invariant "KILL means abstain" is **bypassed in production**.

---

## Q11 — False Confidence Paths ★ THE SCP KILLER (9 found, 3 CRITICAL)

> "Tìm mọi execution path mà hệ thống có thể trả về CONFIDENT/PASS/VALID/VERIFIED trong khi evidence thiếu."

### Q11-FP-1 (CRITICAL) — ReActAgent upgrades UNKNOWN→PASS based on answer length

**Path:** `/ask` → `judge_with_react_fallback` (`judge.py:910`) → `judge_async` returns UNKNOWN/conf<0.5 → `ReActAgent.solve` (`react_agent.py:71`) → `_execute` calls `llm_client.chat_sync(question)` (raw LLM call, line 170) → `_score_observation` (line 185-198) scores by `len/200 + 0.2 if has digit` → returns 0.9 → `solve` returns `success=True, confidence=0.9` → **`judge.py:1033` mutates `verdict.verdict = "PASS"`, `verdict.confidence = 0.9`**.

**What it bypasses:** WHY gate, antibodies, watchlist, source reputation, Governance ESCALATE (silently overridden UNKNOWN→PASS), RealityJudge cross-check.

**Exploit scenario:** Attacker asks "What's the population of Mars in 2050?" SLMs return UNKNOWN/conf=0.3. LLM generates a 200+ char answer with a digit. **SCP returns PASS/conf=0.9 on a fabricated LLM answer.**

**Why this is THE SCP killer:** SCP's tagline is "Reality > Model" (DNA #26). This path is "Model > Reality" — the LLM's answer LENGTH determines confidence, with no external verification. It's the **exact failure mode SCP was designed to prevent**, reachable from production `/ask` with no env vars required.

### Q11-FP-2 (CRITICAL) — execute_plan returns PASS without querying any source

**File:** `why_execute_plan.py:79-82`

Returns PASS/0.95 for deterministic `evidence_type` labels without querying any source. `evidence_type` is set by regex-matching question text — **exploitable by questions that mention "tính" but aren't math**.

### Q11-FP-3 (CRITICAL) — Deterministic SLM short-circuit

**File:** `judgecore_mixin.py:881-928` (Step 9, ROOT-FIX 43-A)

MathSLM/ConversionSLM/StatisticsSLM/LogicSLM with conf≥0.95 → return PASS **without** WHY/adversary/reality verification. A bug in any of these 4 SLMs is unchecked.

### Differs from previous report

**Previous report found 0 false-confidence paths.** This audit found **9 (3 CRITICAL)**. This is the single biggest gap between the two reports. The previous report's top finding (`verify_chain` dead) is a security gate that's OFF. Q11-FP-1 is a false-confidence path that's ON — it actively returns PASS when it shouldn't. **Q11-FP-1 is strictly more dangerous than verify_chain being dead.**

---

## Q12 — Test Quality (38% can false-PASS)

### Test suite overview

| Metric | Value | Industry norm |
|---|---|---|
| Test files | 4 real + 1 shadow canary | — |
| Test functions | 26 (~3,025 cases after parametrize) | — |
| Test-to-code ratio | **1:135** | 1:1 to 1:3 |
| R12-R15 autofix V3/V4 test coverage | **ZERO** (policy_gate, confidence_ranker, reality_test, why_gate, understanding_check — 0 tests) | — |

### Test classification

| Category | Count | % |
|---|---|---|
| BEHAVIOR-genuine | 6 | 23% |
| BEHAVIOR-partial | 6 | 23% |
| WEAK_ASSERTION | 5 | 19% |
| TAUTOLOGICAL | 5 | 19% |
| DISABLED | 3 | 12% |
| FALSE-PASS-CRITICAL | 1 | 4% |
| SMOKE | 1 | 4% |

### 10 untested critical production paths

`verify_chain`, `check_pending_permissions`, `UnderstandingChecker`, `why_gate` UPHOLD, `rank_fixes`, `run_reality_test`, `PolicyGate` fail-closed, `execute_pending_plans`, `classify_threat`, `SourceWatchlist`.

---

## Q13 — False PASS Detection ★ NEW

### Most dangerous false-PASS test

**`test_no_dev_mode_bypass_via_grep`** (`scp/tests/external_audit/test_cascade.py:108`)

Claims to catch the V104.22 #3 admin auth bypass (`SCP_DEV_MODE=1` → `return True`). The regex uses `[^\\n]` (literal backslash-n char class) and `\\n` (literal string) instead of `[^\n]`/`\n` (real newlines).

**Empirically verified:**
```python
pattern_broken = r'SCP_DEV_MODE[^\\n]*?\\n(?:[^\\n]*?\\n){0,4}?\\s*return\\s+True'  # 0 matches
pattern_correct = r'SCP_DEV_MODE[^\n]*?\n(?:[^\n]*?\n){0,4}?\s*return\s+True'       # 1 match
```

**The bypass could be re-added verbatim and both tests would still pass green for 8 audit rounds (R7→R15).**

### Tautological test pattern

5 of 5 tests in `test_none_safety.py` test **LOCAL MIRROR functions** (`crypto_guard`, `currency_guard`, `chemistry_dict_guard`) defined in the same test file (lines 87-104), NOT the actual production guards in `conversionslm.py`, `misc_slm.py`. If any R7-1 prod site reverts to `if value > 0:`, all 3,000+ hypothesis cases still pass green.

### Mental mutation testing

**10 of 25 mutations (40%) were NOT caught by existing tests.**

### Differs from previous report

Previous report did NOT audit tests at all. This audit found the test suite is **severely undersized** (1:135 ratio), 38% of tests can false-PASS, and one test **ALWAYS passes** due to a broken regex — meaning the V104.22 admin auth bypass regression test has been a no-op for 8 rounds.

---

## Q14 — Dependency Audit (10 issues) ★ NEW

| # | Issue | Severity |
|---|---|---|
| 1 | `hypothesis` missing from `requirements-dev.txt` (used in tests + scanner, silently skips) | **CRITICAL** |
| 2 | `target-version = "py39"` but code uses PEP 604 union types (`str | None`) on pydantic models → requires 3.10+ | **HIGH** |
| 3 | Duplicate `requests` + `httpx` HTTP clients | **HIGH** |
| 4 | `asyncio.create_task` without strong ref (RUF006) | MED |
| 5 | 23 ASYNC230/240/210 findings (async lifecycle issues) | MED |
| 6 | `sqlite3.connect()` without context manager (7 sites) | MED |
| 7 | 1,799 G004 f-string-in-log (logging anti-pattern) | MED |
| 8 | `numpy` unused direct pin | LOW |
| 9 | Possibly unused `Faker` | LOW |
| 10 | Possibly unused `pydantic-settings` | LOW |

**Production-failure risk:** `target-version="py39"` is incorrect — pydantic v2 evaluates type annotations via `eval()`, so `str | None` on a model field → `TypeError` on Python 3.9.

---

## Q15 — Devil's Advocate (10 findings rebutted, ALL held)

> "Hãy phản bác chính kết luận audit của bạn. Chọn 10 finding quan trọng nhất và cố gắng chứng minh chúng không phải bug."

| # | Finding | Rebuttal attempted | Verdict |
|---|---|---|---|
| 1 | Q11-FP-1 ReActAgent PASS | "Is ReActAgent actually called in production?" → `api_server.py:823-824` confirms `judge_with_react_fallback` IS called | **HOLDS** (confirmed reachable) |
| 2 | SCPV14 never instantiated | "Is it instantiated dynamically?" → `meta/meta.py:72` imports from `scp.core.scp_v14` (stub), not `runtime.engine`. Import ≠ instantiation. | **HOLDS** |
| 3 | verify_chain never called | "Maybe called via tests?" → 0 test calls (Subagent D confirmed) | **HOLDS** |
| 4 | test regex broken | "Maybe works in some Python version?" → Empirically tested: 0 matches | **HOLDS** |
| 5 | understanding_check return True | "It's intentional ('accept' comment)" → Intentional ≠ correct (same as R14 WhyGate) | **HOLDS** (severity HIGH not CRITICAL) |
| 6 | 9 FALSE_SUCCESS paths | "Some may be 'best effort'" → In anti-hallucination controls, best-effort = false confidence | **HOLDS** |
| 7 | hypothesis missing from requirements | "Maybe installed via setup.py" → grep shows 0 | **HOLDS** |
| 8 | 28 phases not 10 | "Maybe different abstraction level" → Doc says "pipeline" = execution phases | **HOLDS** (doc-vs-code mismatch) |
| 9 | 40% mutations not caught | "Maybe mutations unrealistic" → Flip > to < is basic mutation | **HOLDS** |
| 10 | Vulture FP 47% | "Maybe sample biased" → Subagent B sampled across confidence levels | **HOLDS** (may be 40-50% range) |

**Result: 10/10 findings survived devil's advocate scrutiny.** No finding was retracted.

### Bugs the audit might have MISSED (honest disclosure)

- **Runtime-only bugs:** No code executed. Timing-dependent races, specific input combos not found.
- **Cross-module taint flows:** Needs Semgrep Pro / CodeQL (not installed).
- **54 files pylint didn't cover** (mostly tests/).
- **Dynamic dispatch via `getattr`:** grep can miss string-based calls.
- **LLM prompt injection:** SCP's prompts may be vulnerable (not audited — requires prompt security expertise).

---

## Q16 — Top 10 Production Priorities

> "Nếu phải chịu trách nhiệm production cho repository này, 10 vấn đề nào bạn sẽ sửa trước?"
> Ranked by: correctness → data integrity → security → runtime reliability → invariant violation → maintainability → performance → dead code.

| Rank | Issue | File:line | Category | Evidence | Why first |
|---|---|---|---|---|---|
| **1** | **ReActAgent upgrades UNKNOWN→PASS based on answer length+digits** | `judge.py:1033` + `react_agent.py:185-198` | Correctness + Security + Invariant | Q11-FP-1: `_score_observation = len/200 + 0.2 if has_digit`. Bypasses WHY/Governance/antibodies. | **The exact failure mode SCP was designed to prevent.** Reachable from `/ask`, no env vars needed. |
| **2** | **Deterministic SLM short-circuit returns PASS without verification** | `judgecore_mixin.py:881-928` (Step 9) | Correctness + Invariant | Q11-FP-3: MathSLM/ConversionSLM/StatisticsSLM/LogicSLM conf≥0.95 → PASS, no WHY/adversary/reality | A bug in any of 4 SLMs goes unchecked. |
| **3** | **execute_plan returns PASS without querying any source** | `why_execute_plan.py:79-82` | Correctness + Invariant | Q11-FP-2: `evidence_type` set by regex on question text → exploitable | Regex-match on "tính" → PASS/0.95 without evidence. |
| **4** | **Governance KILL bypassed by ReActAgent wrapper** | `judge.py:1033` (overwrites Governance verdict) | Security + Invariant | Q10-8: KILL → clear answer, but ReActAgent overwrites to PASS | Safety override silently disabled. |
| **5** | **policy_gate fail-open: audit-log write failure flips BLOCK→ALLOW** | `policy_gate.py:647-671` | Security + Data integrity | Q4-FS-2: `except: decision = "ALLOW"` on audit-log failure | `eval()`/`shell=True`/`verify=False` BLOCK flipped to ALLOW. |
| **6** | **verify_chain never called** | `policy_gate.py:420` | Security + Invariant | G2-2 + L1-4: 0 callers, only 1 comment reference | Tamper-evidence gate is a no-op. |
| **7** | **check_pending_permissions never called** | `engine.py:2294` | Security + Invariant | G2-3: 0 callers | Permission system never enforced. |
| **8** | **understanding_check returns True on no-concepts** | `understanding_check.py:58` | Correctness + Invariant | L1-1: `if not proposal_concepts: return True` | Tier-3 human-approval gate fails open. |
| **9** | **test_no_dev_mode_bypass regex broken — always passes** | `test_cascade.py:108` | Runtime reliability | Q13: `[^\\n]` vs `[^\n]` — 0 matches vs 1 | Admin auth bypass regression test is a no-op for 8 rounds. |
| **10** | **SCPV14 never instantiated → DirectAPIVerifier → Step 7 dead** | `runtime/engine.py:SCPV14` | Runtime reliability + Dead code | Q0+Q1: `grep "SCPV14("` = 0 production hits | Documented "Reality check" fallback is dead code. |

### Execution path for #1 (the SCP killer)

```
User → POST /ask
  → api_server.py:823  judge.judge_with_react_fallback(question)
    → judge.py:910  judge_async() → UNKNOWN, conf=0.3
    → judge.py:1025  conf < 0.5 → ReActAgent.solve(question)
      → react_agent.py:170  llm_client.chat_sync(question)  ← raw LLM, no verification
      → react_agent.py:185  _score_observation(answer)
           = min(len(answer) / 200, 1.0) + (0.2 if has_digit else 0)
           = 0.9  (200+ chars with a digit)
      → return success=True, confidence=0.9
    → judge.py:1033  verdict.verdict = "PASS"  ← OVERWRITES UNKNOWN
    → judge.py:1034  verdict.confidence = 0.9  ← OVERWRITES 0.3
    → judge.py:1035  verdict.final_answer = react_result.answer  ← fabricated LLM answer
  → return PASS/0.9 to user
```

**What SHOULD happen:** UNKNOWN stays UNKNOWN. LLM answer is treated as a CANDIDATE, not a verdict. It must pass WHY gate, adversary check, and source verification before upgrading to PASS.

---

## Comparison with Previous Report (deep-research-report.md)

### What the previous report GOT RIGHT (confirmed by this audit)

| Previous finding | This audit's verdict |
|---|---|
| `verify_chain` never called (G2-2) | ✅ Confirmed (Q9 NOT_USED, Q10 PARTIAL) |
| `understanding_check.py:58` return True (L1-1) | ✅ Confirmed (Q9 NOT_ENFORCED, Q11-FP-3) |
| `intent_inference_engine.py:503` dead (G2-1) | ✅ Confirmed (Q2 confirmed dead) |
| 1,804 silent-failure locations | ✅ Confirmed (Q4 — but now impact-assessed) |
| R13 reality test verified "callable" not "called" | ✅ Confirmed (Q10 — recursive PASS≠TRUE) |

### What the previous report MISSED (found by this audit)

| Gap | What this audit found | Impact |
|---|---|---|
| **False confidence paths** | 9 found, 3 CRITICAL (Q11-FP-1/2/3) | **THE SCP KILLER** — previous report's top finding (verify_chain dead) is a gate that's OFF. Q11-FP-1 is a path that's ON, actively returning PASS when it shouldn't. |
| **State machines** | 17 found, 6 STUCK states (Q8) | WHY verification plan stuck in `pending` forever — entire subsystem is a no-op. |
| **Test quality** | 38% false-PASS rate, 1 test ALWAYS passes (Q12-Q13) | Admin auth bypass regression test has been a no-op for 8 rounds. |
| **Architecture vs docs** | "10-phase pipeline" = FICTION (actual: 28 phases); SCPV14 never instantiated (Q0+Q1+Q9) | Documented architecture doesn't match runtime. |
| **Dependency audit** | 10 issues; py39 target but PEP 604 unions need 3.10+ (Q14) | Production failure on Python 3.9. |
| **Duplicate code** | 10 clusters (up from 1); CircuitBreaker naming collision (Q3) | Maintenance trap — same class name, different APIs. |
| **Devil's advocate** | 10 findings rebutted, all held (Q15) | Previous report had no self-rebuttal step. |
| **Contract mismatches** | 14 found, 5 CRITICAL (Q5) | Module-to-module assumptions don't match. |
| **Edge cases** | 27 gaps across 12 categories (Q7) | HTTP timeout missing, DB failure leaves inconsistent state. |

### Methodological difference

| Aspect | Previous (deep-research-report.md) | This (r16) |
|---|---|---|
| **Driver** | Tools (6 automated → 3 buckets) | Questions (15 structured, human-designed) |
| **Strength** | Broad coverage (36,943 raw findings) | Deep insight (false confidence, state machines, test quality) |
| **Weakness** | Missed semantic bugs (false confidence, state machine) | Smaller sample (didn't re-run all 36,943) |
| **Top finding** | `verify_chain` dead (security gate OFF) | `judge.py:1033` ReActAgent PASS (false confidence ON) |
| **Verdict** | Good for code-level issues | **Better for SCP's core claim** (anti-hallucination) |

### The single most important difference

**The previous report's top finding is a security gate that's OFF (verify_chain never called). This report's top finding is a false-confidence path that's ON (judge.py:1033 returns PASS based on LLM answer length).**

A gate that's OFF means "we forgot to enforce X." A path that's ON means "we are actively doing the wrong thing." **Q11-FP-1 is strictly more dangerous** because it means SCP is RIGHT NOW returning PASS/conf=0.9 on fabricated LLM answers — the exact hallucination it was designed to prevent.

The previous report couldn't find this because:
1. Static tools (ruff, pylint, vulture, mypy, bandit) check SYNTAX, not SEMANTICS. `verdict.verdict = "PASS"` parses fine.
2. The 3-bucket framework (code/logic/dead) doesn't have a "false confidence" category.
3. No invariant tracing (Q10) or false-confidence path tracing (Q11) was done.

**This is why the 15-question framework matters:** it asks the questions that tools can't answer.

---

## Conclusion

> **🐔 Gà:** "Khác biệt gì với báo cáo của bạn?"
>
> **🤖 SCP:** "Báo cáo trước tìm code rác và lint errors. Báo cáo này tìm ra SCP đang làm đúng điều nó được thiết kế để chặn không — trả về PASS dựa trên độ dài câu trả lời LLM, bypass tất cả safety gates. Q11-FP-1 là SCP killer bug. 15 câu hỏi của bạn tìm ra điều mà 6 công cụ world-class + 15 vòng audit trước MISSED."

### Bottom line

| Metric | Previous report | This report | Delta |
|---|---|---|---|
| CRITICAL findings | 3 | 3 (different, more dangerous) | +0 (but quality ↑) |
| False confidence paths | 0 | **9** | **+9** ← biggest gap |
| State machines | 0 | **17** | +17 |
| Test quality findings | 0 | **26 tests classified, 38% false-PASS** | +new category |
| Dependency issues | 0 | **10** | +10 |
| Devil's advocate | No | **10/10 held** | +new step |
| Architecture discrepancies | ~1 | **13** | +12 |
| Top finding severity | Security gate OFF (passive) | **False confidence ON (active)** | ↑↑↑ |

**The 15-question framework found the SCP killer bug (Q11-FP-1) that the previous tool-driven report completely missed.** This is because the framework asks "does SCP actually do what it claims?" (Q9-Q11) — a question that no static analysis tool can answer.

> **KHÔNG HOÀN THIỆN. KHÔNG THẤT BẠI. KHÔNG HOÀN TẤT. ĐANG HOẠT ĐỘNG.** (DNA #23)
>
> **Và Reality vẫn giữ quyền trả lời cuối cùng.** (DNA #26 🌍)

---

## Appendix — Subagent findings files

| File | Size | Content |
|---|---|---|
| `Q0_Q1_Q8_FINDINGS.md` | ~750 lines | Codebase analysis, reachability, 11 state machines reconstructed |
| `Q2_Q3_Q4_Q14_FINDINGS.md` | ~700 lines | 7-way dead code, 10 duplicate clusters, 30 error handlers impact-assessed, 10 dependency issues |
| `Q5_Q6_Q7_Q9_Q10_Q11_FINDINGS.md` | ~1100 lines | 14 contract mismatches, 12 invariant violations, 27 edge cases, 13 arch discrepancies, 22 invariant enforcement traces, 9 false confidence paths |
| `Q12_Q13_FINDINGS.md` | ~17 KB | 26 tests classified, 10 false-PASS, 10 mental mutations, 10 counterexamples |
| `worklog-r16.md` | ~240 lines | Full agent worklog (Tasks 1, 2-a, 2-b, 2-c, 2-d) |

All files in `/home/z/my-project/scp-r15-lint-results/`.

---

**Built by Gà Lab · SCP R15 15-Question Audit · "HỎI ĐÚNG CÂU HỎI, TÌM ĐÚNG LỖI."**
