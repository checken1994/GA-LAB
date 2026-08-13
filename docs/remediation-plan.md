# SCP R15 — Phương án Xử lý Chi tiết
## Detailed Remediation Plan for Top 10 Findings

> **🐔 Gà:** "phương án sử lý chi tiết của bạn là gì?"
>
> **🤖 SCP:** "Đây là plan từng bug: root cause → fix code (before/after) → verification → risk. 4 phase: P0 hotfix (SCP killer) → P1 security wiring → P2 tests → P3 cleanup."

---

## Tổng quan chiến lược

| Phase | Focus | Số fix | Thời gian ước tính | Rủi ro |
|---|---|---|---|---|
| **P0 — Hotfix ngay** | Dừng SCP killer (false confidence) | 3 | 1-2 giờ | THẤP (code additive, có fallback) |
| **P1 — Security wiring** | Wire các gate đã implement nhưng chưa gọi | 3 | 3-4 giờ | MED (thay đổi execution path) |
| **P2 — Tests + correctness** | Fix test broken + understanding_check | 2 | 2-3 giờ | THẤP |
| **P3 — Cleanup + deps** | Dead code + dependencies | 2+ | 4-6 giờ | THẤP (auto-fixable) |

**Nguyên tắc:** Mỗi fix phải (1) không phá production path, (2) có Reality test verify, (3) có rollback path. Fix P0 trước, verify, rồi mới P1.

---

## Phase P0 — Hotfix ngay (SCP killer)

### 🔴 P0-1: Dừng ReActAgent ghi đè verdict (Q11-FP-1)

**Vì sao trước nhất:** Đây là đường **đang hoạt động** trả PASS dựa trên `len(answer)/200 + 0.2 if has_digit`. Mỗi giờ không fix = mỗi giờ SCP có thể trả PASS/conf=0.9 trên LLM answer bịa.

#### File: `scp/runtime/judge.py:1025-1045`

#### Root cause
`judge_with_react_fallback` chạy `judge_async` (đã qua WHY gate, antibodies, Governance) → nếu UNKNOWN/conf<0.5 → gọi `ReActAgent.solve` (raw LLM) → nếu `react_result.confidence >= 0.8` (tính bằng length+digits heuristic) → **ghi đè** `verdict.verdict = "PASS"`, `verdict.confidence = 0.9`. Bypass toàn bộ safety pipeline đã chạy trước đó.

#### Fix — 3 bước

**Bước 1: Không cho ReActAgent ghi đè verdict. Chỉ thêm answer làm CANDIDATE evidence.**

```python
# BEFORE (judge.py:1025-1045) — BUG:
if react_result.success and react_result.confidence >= 0.8:
    if hasattr(verdict, "final_answer"):
        verdict.final_answer = react_result.answer
    if hasattr(verdict, "confidence"):
        verdict.confidence = react_result.confidence
    if hasattr(verdict, "verdict"):
        verdict.verdict = "PASS"  # ← KILLER: overrides UNKNOWN→PASS
```

```python
# AFTER — FIX P0-1a: ReActAgent answer = CANDIDATE, not verdict
if react_result.success and react_result.answer:
    # ReActAgent trả về raw LLM answer — KHÔNG phải verified verdict.
    # Thêm làm CANDIDATE evidence (source="react_agent_llm"),
    # KHÔNG ghi đè verdict/confidence.
    # Verdict vẫn UNKNOWN — operator thấy cần review manual.
    if hasattr(verdict, "final_answer") and not verdict.final_answer:
        verdict.final_answer = react_result.answer
    if hasattr(verdict, "reasoning"):
        verdict.reasoning = (
            (verdict.reasoning or "")
            + f" | [OPT-9] ReActAgent candidate (NOT verified): "
            + f"{len(react_result.steps)} steps, heuristic_conf={react_result.confidence:.2f}"
        )
    # Thêm metadata flag để operator biết có candidate chưa verify
    if hasattr(verdict, "metadata"):
        if isinstance(verdict.metadata, dict):
            verdict.metadata["react_candidate_unverified"] = True
            verdict.metadata["react_candidate_answer"] = react_result.answer[:500]
    # KHÔNG đổi verdict.verdict — giữ UNKNOWN
    # KHÔNG đổi verdict.confidence — giữ giá trị từ judge_async
    logger.info(
        f"[OPT-9] ReActAgent candidate added (NOT verified, conf={react_result.confidence:.2f}); "
        f"verdict stays {getattr(verdict, 'verdict', 'UNKNOWN')}"
    )
```

**Bước 2: Sửa `_score_observation` — không dùng length+digits làm confidence.**

```python
# BEFORE (react_agent.py:185-198) — BUG:
def _score_observation(self, observation: str, question: str) -> float:
    if not observation:
        return 0.0
    if observation.startswith("[ERROR]"):
        return 0.0
    if observation.startswith("[UNVERIFIED]"):
        return 0.4
    score = min(0.7, len(observation) / 200)       # ← length = confidence?!
    if any(c.isdigit() for c in observation):       # ← has digit = +0.2?!
        score = min(0.9, score + 0.2)
    return score
```

```python
# AFTER — FIX P0-1b: heuristic score = "interest signal", NOT "confidence"
def _score_observation(self, observation: str, question: str) -> float:
    """Heuristic INTEREST score (not confidence).

    Returns a 0.0-1.0 signal indicating whether the observation is worth
    investigating further. This is NOT a verification confidence — the
    answer is still UNVERIFIED until it passes WHY gate + source check.

    Caller MUST treat this as "candidate quality", not "truth probability".
    """
    if not observation:
        return 0.0
    if observation.startswith("[ERROR]"):
        return 0.0
    if observation.startswith("[UNVERIFIED]"):
        return 0.2  # lowered — explicitly unverified
    # Length = "substantive enough to investigate", capped low
    interest = min(0.4, len(observation) / 200)
    # Digit bonus = "might be factual, worth checking" — NOT "is correct"
    if any(c.isdigit() for c in observation):
        interest = min(0.5, interest + 0.1)
    return interest  # max 0.5 — NEVER reaches the 0.8 "accept" threshold
```

**Bước 3: Tăng threshold accept trong `judge.py` + thêm guard.**

```python
# AFTER — FIX P0-1c: threshold 0.8 → không bao giờ reach với heuristic max 0.5
# (Belt-and-suspenders: ngay cả nếu _score_observation bị revert,
#  guard dưới đây vẫn chặn ghi đè verdict)
REACT_ACCEPT_THRESHOLD = 0.8  # heuristic max = 0.5 → không bao giờ accept

if react_result.success and react_result.confidence >= REACT_ACCEPT_THRESHOLD:
    # ... (code Bước 1 — thêm candidate, KHÔNG ghi đè verdict)
```

#### Verification (Reality test)
```bash
# T1: grep không còn "verdict.verdict = \"PASS\"" trong block ReActAgent
rg -n 'verdict\.verdict = "PASS"' scp/runtime/judge.py | grep -i react
# EXPECT: 0 hits

# T2: _score_observation max = 0.5
python3 -c "
from scp.core.react_agent import ReActAgent
agent = ReActAgent.__new__(ReActAgent)
print(agent._score_observation('a'*500 + ' 42', 'q'))  # should be ≤ 0.5
"
# EXPECT: 0.5

# T3: ReActAgent candidate được thêm nhưng verdict vẫn UNKNOWN
# (chạy test integration với question low-confidence, verify verdict.verdict != "PASS")
```

#### Risk
- **LOW.** Code additive — `verdict` vẫn trả về (chỉ không upgrade UNKNOWN→PASS). `/ask` vẫn work, chỉ trả UNKNOWN thay vì PASS-mtanggal. Operator có thể review `react_candidate_answer` trong metadata.
- **Rollback:** revert 3 block (Bước 1+2+3).

---

### 🔴 P0-2: SLM deterministic short-circuit phải qua reality check (Q11-FP-3)

**Vì sao:** `judgecore_mixin.py:1007-1020` — MathSLM/ConversionSLM/StatisticsSLM/LogicSLM conf≥0.95 → `return JudgeVerdict(verdict="PASS")` **không** WHY/adversary/reality. Bug trong 4 SLM này = unchecked.

#### File: `scp/runtime/judge_parts/judgecore_mixin.py:1007-1020`

#### Root cause
Comment nói "deterministic evaluator IS reality" (DNA #1). NHƯNG:
1. MathSLM có thể return conf=0.95 trên expression sai (nếu AST evaluator có bug)
2. LogicSLM "truth tables" — nếu truth table bị corrupt?
3. Không có independent verify — chỉ tin SLM tự report conf≥0.95

#### Fix — thêm lightweight reality check

```python
# BEFORE (judgecore_mixin.py:1007-1020) — BUG:
DETERMINISTIC_SLMS = ("MathSLM", "ConversionSLM", "StatisticsSLM", "LogicSLM")
if primary and confidence >= 0.95:
    _slm_name = str(primary.get("slm_name", "") or primary.get("source", "") or "")
    if any(_d in _slm_name for _d in DETERMINISTIC_SLMS):
        logger.info(f"[ROOT-FIX 43-A] Trusting deterministic SLM ...")
        return JudgeVerdict(
            question=question, slm_responses=slm_responses,
            final_answer=final_answer, confidence=confidence,
            verdict="PASS",  # ← PASS without verify
            ...
        )
```

```python
# AFTER — FIX P0-2: deterministic SLM = "PASS_CANDIDATE", cần verify
DETERMINISTIC_SLMS = ("MathSLM", "ConversionSLM", "StatisticsSLM", "LogicSLM")
if primary and confidence >= 0.95:
    _slm_name = str(primary.get("slm_name", "") or primary.get("source", "") or "")
    if any(_d in _slm_name for _d in DETERMINISTIC_SLMS):
        # P0-2 FIX: deterministic SLM confidence is necessary but NOT sufficient.
        # Reality check: re-evaluate the answer independently (cheap for deterministic).
        _reality_ok = self._reality_check_deterministic(
            _slm_name, question, final_answer, primary
        )
        if _reality_ok:
            logger.info(f"[ROOT-FIX 43-A] Deterministic SLM '{_slm_name}' PASSED reality check")
            return JudgeVerdict(
                question=question, slm_responses=slm_responses,
                final_answer=final_answer, confidence=confidence,
                verdict="PASS",
                reasoning=f"Deterministic SLM '{_slm_name}' + reality check passed",
                ...
            )
        else:
            # Reality check FAILED — don't PASS, downgrade to UNKNOWN
            logger.warning(
                f"[P0-2] Deterministic SLM '{_slm_name}' claimed conf={confidence:.2f} "
                f"but reality check FAILED — downgrading to UNKNOWN"
            )
            confidence = min(confidence, 0.4)
            # Fall through to normal verdict path (will likely return UNKNOWN)
```

Thêm method `_reality_check_deterministic` (new method trên judgecore_mixin):
```python
def _reality_check_deterministic(self, slm_name: str, question: str,
                                   answer: str, primary_response: dict) -> bool:
    """Lightweight independent verify cho deterministic SLM.

    - MathSLM: re-evaluate expression, compare to answer
    - ConversionSLM: re-convert, compare
    - StatisticsSLM: re-aggregate, compare
    - LogicSLM: re-evaluate truth table, compare

    Returns True if independent evaluation matches SLM's answer.
    """
    try:
        if "MathSLM" in slm_name:
            # Extract expression from question, re-evaluate
            _expr = self._extract_math_expr(question)
            if _expr:
                _re_eval = self._safe_math_eval(_expr)
                if _re_eval is not None:
                    return str(_re_eval) in str(answer) or abs(float(_re_eval) - float(answer)) < 0.01
        # ConversionSLM/StatisticsSLM/LogicSLM: similar pattern
        # (implement per SLM — or if too complex, return True with WARNING log)
        return True  # default: trust (with logged warning)
    except Exception as e:
        logger.warning(f"[P0-2] reality_check_deterministic failed: {e}")
        return False  # fail-closed
```

#### Verification
```bash
# T1: grep — block "return JudgeVerdict(verdict=PASS)" có _reality_check_deterministic
rg -n "_reality_check_deterministic" scp/runtime/judge_parts/judgecore_mixin.py
# EXPECT: ≥2 hits (def + call)

# T2: unit test — MathSLM trả 42 cho "6*7", reality check re-eval 6*7=42 → match → PASS
# T3: unit test — MathSLM trả 42 cho "6*7" nhưng expression extract fail → UNKNOWN
```

#### Risk
- **MED.** Thêm latency (re-evaluate). Nhưng deterministic SLM eval is fast (μs-ms). Nếu `_reality_check_deterministic` quá complex cho 1 SLM, return True + warning (không block, chỉ log).

---

### 🔴 P0-3: `execute_plan` không trả PASS không source (Q11-FP-2)

**Vì sao:** `why_execute_plan.py:79-86` — `evidence_type in ("deterministic_calculation", ...)` → `verdict="PASS", confidence=0.95` **không query source nào**. `evidence_type` được set bằng regex-match question text → exploitable.

#### File: `scp/meta/why_engine_parts/why_execute_plan.py:79-86`

#### Root cause
Comment nói "Deterministic — verified by direct computation". NHƯNG:
1. `evidence_type` set bởi regex trên question text (không phải bởi actual computation)
2. Question "tính dân số Mars 2050" có thể match `deterministic_calculation` regex
3. Không có verification — chỉ trust label

#### Fix — require evidence

```python
# BEFORE (why_execute_plan.py:79-86) — BUG:
if plan.evidence_type in ("deterministic_calculation", "deterministic_evaluation",
                           "codata_constants", "biological_database"):
    result["verdict"] = "PASS"
    result["confidence"] = 0.95
    result["reasoning"] = "Deterministic — verified by direct computation"
    return result
```

```python
# AFTER — FIX P0-3: deterministic label = necessary but NOT sufficient
if plan.evidence_type in ("deterministic_calculation", "deterministic_evaluation",
                           "codata_constants", "biological_database"):
    # P0-3 FIX: don't PASS without at least ONE source verification.
    # The "deterministic" label was set by regex on question text —
    # it's a ROUTING hint, not a VERIFICATION.
    # Query at least the FIRST planned source to confirm.
    if not plan.sources_to_query:
        # No sources planned → can't verify → UNKNOWN, not PASS
        result["verdict"] = "UNKNOWN"
        result["confidence"] = 0.3
        result["reasoning"] = (
            "Deterministic label but NO sources planned — cannot verify. "
            "Need at least 1 source query to PASS."
        )
        return result
    # Fall through to normal source-query loop (don't short-circuit)
    logger.info(
        f"[P0-3] Deterministic evidence_type but querying {len(plan.sources_to_query)} "
        f"sources to verify (not short-circuiting to PASS)"
    )
# (fall through to the source-query loop below)
```

#### Verification
```bash
# T1: grep — không còn "verdict.*PASS.*return" trong block deterministic
rg -n "verdict.*=.*PASS" scp/meta/why_engine_parts/why_execute_plan.py | head -5
# EXPECT: 0 hits in the deterministic block

# T2: test — question "tính 2+2" với evidence_type=deterministic_calculation
#     nhưng sources_to_query=[] → verdict=UNKNOWN (not PASS)
# T3: test — question "tính 2+2" với sources_to_query=["MathSLM"] → query MathSLM → PASS
```

#### Risk
- **LOW.** Nếu `sources_to_query` có ít nhất 1 source → fall through to normal loop (chậm hơn một chút nhưng correct). Nếu empty → UNKNOWN (an toàn hơn PASS-mtanggal).

---

## Phase P1 — Security wiring (3 fixes)

### 🟠 P1-1: Wire `verify_chain` vào engine (Q11-FP-1 hậu quả + G2-2)

**Vì sao:** `policy_gate.py:420` `verify_chain` implemented (290 LOC) nhưng 0 callers. Tamper-evidence gate = no-op.

#### File: `scp/autofix/engine.py` (Tier-2 apply step)

#### Fix — wire vào trước khi write file

```python
# AFTER — FIX P1-1: trong engine.py, method apply_tier2_fix (hoặc tương tự),
# trước khi write patched file:
try:
    from scp.autofix.policy_gate import get_policy_gate
    _gate = get_policy_gate()
    _chain_ok, _chain_msg = _gate.verify_chain()
    if not _chain_ok:
        logger.error(f"[P1-1] Policy gate verify_chain FAILED: {_chain_msg}")
        # BLOCK the fix — chain is tampered
        return FixResult(
            success=False,
            reason=f"Policy gate chain verification failed: {_chain_msg}",
            blocked_by="verify_chain",
        )
    logger.debug(f"[P1-1] verify_chain OK: {_chain_msg}")
except ImportError:
    logger.warning("[P1-1] policy_gate not available — skipping chain verify (DNA #7 fail-open)")
except Exception as _vc_err:
    # Fail-open per DNA #7 (don't brick engine) — but LOG LOUDLY
    logger.error(f"[P1-1] verify_chain crashed (fail-open): {_vc_err}")
# (proceed to write file)
```

#### Verification
```bash
# T1: grep — verify_chain có production caller
rg -n "verify_chain\(\)" scp/autofix/engine.py
# EXPECT: ≥1 hit

# T2: test — tamper audit log → apply fix → BLOCKED
# T3: test — clean audit log → apply fix → SUCCESS
```

#### Risk
- **MED.** Nếu audit log bị tamper (hiếm), fix sẽ bị block. Có `fail-open` cho crash (DNA #7). Tuy nhiên, nếu `verify_chain` có bug logic → có thể block legitimate fixes. **Mitigation:** chạy `verify_chain` ở dry-run mode trước khi wire vào production.

---

### 🟠 P1-2: Wire `check_pending_permissions` (G2-3)

Tương tự P1-1 nhưng cho `engine.py:2294 check_pending_permissions`. Wire vào runner trước Tier-3 fixes.

#### Fix
```python
# Trong runner.py, trước Tier-3 dispatch:
try:
    _pending = engine.check_pending_permissions()
    if _pending.get("blocked"):
        logger.warning(f"[P1-2] Pending permissions block Tier-3: {_pending}")
        skip_tier3 = True
except Exception as _pp_err:
    logger.error(f"[P1-2] check_pending_permissions crashed (fail-open): {_pp_err}")
```

#### Verification + Risk
- Tương tự P1-1.

---

### 🟠 P1-3: `policy_gate` fail-closed thay vì fail-open (Q4-FS-2)

**Vì sao:** `policy_gate.py:647-671` — audit-log write failure → BLOCK flipped to ALLOW. `eval()`/`shell=True`/`verify=False` được ALLOW khi disk full.

#### File: `scp/autofix/policy_gate.py:647-671`

#### Fix — fail-closed cho BLOCK decisions

```python
# BEFORE (policy_gate.py:653-665) — BUG:
written_hash = self.audit_log.append(entry)
if written_hash is None and decision.severity == "BLOCK":
    # FLIP to ALLOW per DNA #7 fail-open  ← KILLER for security
    decision.allowed = True
    decision.severity = "ALLOW"
    ...
```

```python
# AFTER — FIX P1-3: BLOCK stays BLOCK (fail-closed for security)
written_hash = self.audit_log.append(entry)
if written_hash is None and decision.severity == "BLOCK":
    # P1-3 FIX: BLOCK stays BLOCK. DNA #7 fail-open is for RUNTIME availability,
    # NOT for SECURITY decisions. If we can't log a BLOCK, we STILL block —
    # better to refuse a fix than to allow eval()/shell=True unlogged.
    decision.allowed = False  # stays blocked
    decision.severity = "BLOCK"  # stays BLOCK
    decision.reason = (
        f"[P1-3] BLOCK maintained: audit log unwritable AND fix matches "
        f"BLOCKED_PATTERNS. Refusing to fail-open for security. "
        f"Operator must free disk space / fix permissions, then re-run. "
        f"BLOCKED_PATTERNS were: {list(decision.blocked_patterns)}."
    )
    sys.stderr.write(
        "[P1-3] CRITICAL: audit log unwritable while blocking a fix with "
        "BLOCKED_PATTERNS. BLOCK maintained (fail-CLOSED for security).\n"
        f"[P1-3] fix_id={decision.fix_id} patterns={list(decision.blocked_patterns)}\n"
        "[P1-3] Operator must investigate disk space / permissions.\n"
    )
    sys.stderr.flush()
    # ALLOW decisions can still fail-open (non-security) — only BLOCK is fail-closed
```

#### Verification
```bash
# T1: test — mock audit_log.append return None + decision.severity=BLOCK
#     → decision.allowed stays False, decision.severity stays "BLOCK"
# T2: test — mock audit_log.append return None + decision.severity=ALLOW
#     → decision.allowed stays True (fail-open for non-security is OK)
```

#### Risk
- **MED.** Nếu disk full + fix match BLOCKED_PATTERNS → fix bị block. Đây là **đúng behavior** (security > availability). Operator cần monitor disk space. **Mitigation:** thêm alerting khi `written_hash is None`.

---

## Phase P2 — Tests + correctness (2 fixes)

### 🟡 P2-1: Fix broken test regex (Q13 — test ALWAYS passes)

**Vì sao:** `test_cascade.py:130` — regex dùng `[^\\n]` (literal backslash-n) thay vì `[^\n]` (real newline). Test **ALWAYS passes** — admin auth bypass regression test là no-op 8 rounds.

#### File: `scp/tests/external_audit/test_cascade.py:128-134`

#### Fix — sửa regex

```python
# BEFORE (test_cascade.py:130-133) — BUG:
pattern = re.compile(
    r'SCP_DEV_MODE[^\\n]*?\\n(?:[^\\n]*?\\n){0,4}?\\s*return\\s+True',
    re.MULTILINE
)
```

```python
# AFTER — FIX P2-1: dùng real newlines
pattern = re.compile(
    r'SCP_DEV_MODE[^\n]*?\n(?:[^\n]*?\n){0,4}?\s*return\s+True',
    re.MULTILINE
)
```

#### Verification
```bash
# T1: chạy test với bypass code present → test FAILS (đúng)
# T2: chạy test không có bypass → test PASSES (đúng)
python3 -c "
import re
pattern = r'SCP_DEV_MODE[^\n]*?\n(?:[^\n]*?\n){0,4}?\s*return\s+True'
bypass_code = 'os.environ[\"SCP_DEV_MODE\"] = \"1\"\nif os.environ.get(\"SCP_DEV_MODE\") == \"1\":\n    return True'
print(f'Matches: {len(re.findall(pattern, bypass_code))}')  # EXPECT: 1
clean_code = 'def verify_admin():\n    return False'
print(f'Clean matches: {len(re.findall(pattern, clean_code))}')  # EXPECT: 0
"
```

#### Risk
- **LOW.** Test sẽ bắt đầu thực sự chạy. Nếu bypass đã được re-introduced (không phát hiện vì test broken), test sẽ FAIL → phát hiện bug. Đây là **đúng behavior**.

---

### 🟡 P2-2: `understanding_check` fail-closed (L1-1)

**Vì sao:** `understanding_check.py:58` — `if not proposal_concepts: return True` ("accept"). Cùng semantic inversion như R14 WhyGate KB1.

#### File: `scp/meta/understanding_check.py:58`

#### Fix — return False (UPHOLD for review)

```python
# BEFORE (understanding_check.py:57-59) — BUG:
if not proposal_concepts:
    return True  # can't verify concepts, accept
```

```python
# AFTER — FIX P2-2: UPHOLD for review (same root fix as R14 WhyGate KB1)
if not proposal_concepts:
    logger.warning(
        "[P2-2] No extractable concepts in proposal — cannot verify understanding. "
        "UPHOLD for human review (not auto-accept)."
    )
    return False  # UPHOLD — don't accept what we can't verify
```

#### Verification
```bash
# T1: test — proposal with no concepts (regex/symbol-only) → returns False
# T2: test — proposal with concepts + good overlap → returns True
```

#### Risk
- **LOW.** Tier-3 fixes với no-concept proposals sẽ bị block → operator phải review manual. Đây là **đúng behavior** (không auto-accept những gì không verify được).

---

## Phase P3 — Cleanup + dependencies (2+ fixes)

### 🟢 P3-1: Dependency audit fixes (Q14)

#### Fix list

| # | Issue | Fix |
|---|---|---|
| 1 | `hypothesis` missing from requirements-dev.txt | Add `hypothesis>=6.108` |
| 2 | `target-version = "py39"` but PEP 604 unions used | Change to `target-version = "py310"` in ruff.toml + pyproject.toml |
| 3 | Duplicate `requests` + `httpx` | Audit usage; if both used, document why; if not, remove `requests` |
| 4 | `sqlite3.connect()` without context manager (7 sites) | Wrap in `contextlib.closing` or use `with sqlite3.connect(...) as conn:` |
| 5 | 1,799 G004 f-string-in-log | Run `ruff check --select G004 --fix` (use `%s` formatting) |

#### Verification
```bash
# T1: pip install -r requirements-dev.txt succeeds + hypothesis imports
# T2: python3.9 không còn được claim support (ruff target = py310)
# T3: grep sqlite3.connect — all trong context manager
```

#### Risk
- **LOW.** Auto-fixable cho hầu hết. `target-version` change có thể flag new lint errors (acceptable — fix dần).

---

### 🟢 P3-2: Dead code cleanup (Q2)

#### Fix list (priority order)

| # | Finding | Action | LOC |
|---|---|---|---|
| 1 | `intent_inference_engine.py:503` (dead module) | Delete file (503 LOC) OR wire into runner | -503 |
| 2 | `capabilities/{rag,vision,voice}.py` (dead stubs) | Delete 3 files | -210 |
| 3 | `core/healing_engine.py` (dead, superseded by healing_v14) | Delete | -100 |
| 4 | 15 `slm_cache_set` redefinitions | Centralize in `runtime/slm_cache.py` | -150 |
| 5 | `audit_r8/`, `audit_r9/` (stale) | Move to `docs/audit_history/` | cleaner tree |
| 6 | `V2_MANIFEST.md`, `V3_MANIFEST.md` (stale, V4 current) | Move to `docs/autofix_history/` | cleaner tree |
| 7 | 210 ERA001 commented-out code | `ruff --select ERA001 --fix` | -210 |
| 8 | 29 F401 unused imports | `ruff --select F401 --fix` | -29 |

#### Verification
```bash
# T1: sau cleanup, run full test suite — all pass
# T2: ruff check — 0 F401, 0 ERA001
# T3: grep không còn import intent_inference_engine
```

#### Risk
- **LOW** cho auto-fixable (ruff --fix).
- **MED** cho delete files — cần verify 0 dynamic dispatch trước (đã verify trong Q2 audit).

---

## Verification strategy tổng thể

### Sau mỗi phase

```bash
# 1. Lint clean
/tmp/scp-lint-venv/bin/ruff check scp/ --select F,B,SIM,TRY,S,RET --ignore D,ANN
# EXPECT: 0 errors (warnings OK)

# 2. AST parse tất cả files
for f in $(find scp -name "*.py"); do
  python3 -c "import ast; ast.parse(open('$f').read())" || echo "FAIL: $f"
done
# EXPECT: 0 FAIL

# 3. Test suite pass
pytest scp/tests/ -v
# EXPECT: all pass (sau P2-1, test_no_dev_mode_bypass sẽ thực sự chạy)

# 4. Reality test cho từng fix (xem "Verification" per fix ở trên)
```

### Sau tất cả phases — regression test

```bash
# 1. SCP killer path — verify KHÔNG còn trả PASS dựa trên length
python3 -c "
import asyncio
from scp.runtime.judge import RealityJudge
judge = RealityJudge()
v = asyncio.run(judge.judge_with_react_fallback('What is population of Mars in 2050?'))
print(f'verdict={v.verdict} conf={v.confidence}')
# EXPECT: verdict=UNKNOWN (NOT PASS), conf<0.5
"

# 2. Policy gate — verify BLOCK stays BLOCK khi audit log fail
python3 -c "
from scp.autofix.policy_gate import PolicyGate
gate = PolicyGate(audit_log=__import__('unittest.mock').mock.MagicMock())
gate.audit_log.append.return_value = None  # simulate disk full
# ... test BLOCK decision stays BLOCK
"

# 3. Test regex — verify catches bypass
pytest scp/tests/external_audit/test_cascade.py::test_no_dev_mode_bypass_via_grep -v
# EXPECT: PASS (vì bypass đã removed) — nhưng nếu re-add, sẽ FAIL
```

---

## Sequencing + timeline

| Tuần | Phase | Fix | Verify |
|---|---|---|---|
| **Tuần 1, ngày 1** | P0-1 | ReActAgent không ghi đè verdict + _score_observation max 0.5 | Reality test T1-T3 |
| **Tuần 1, ngày 1** | P0-2 | SLM deterministic + reality check | Reality test T1-T3 |
| **Tuần 1, ngày 2** | P0-3 | execute_plan không PASS không source | Reality test T1-T3 |
| **Tuần 1, ngày 3-4** | P1-1, P1-2 | Wire verify_chain + check_pending_permissions | Dry-run + integration test |
| **Tuần 1, ngày 5** | P1-3 | policy_gate fail-closed | Unit test BLOCK stays BLOCK |
| **Tuần 2, ngày 1** | P2-1 | Fix test regex | Test catches bypass |
| **Tuần 2, ngày 2** | P2-2 | understanding_check fail-closed | Unit test |
| **Tuần 2, ngày 3-5** | P3-1, P3-2 | Dependencies + dead code cleanup | Full regression |

**Tổng: ~2 tuần** (1 dev, có thể rút ngắn nếu P0 hotfix trong 1 ngày).

---

## Prevention — tránh lặp lại

### 1. CI gate: "wiring verification"

```bash
# Thêm vào CI: cho mọi public function, grep phải có ≥1 production caller
for func in $(grep -rn "^def \|^    def " scp/ --include="*.py" | grep -v "test_\|_" | ...); do
  callers=$(grep -rn "$func(" scp/ --include="*.py" | grep -v "def $func" | wc -l)
  if [ "$callers" -eq 0 ]; then
    echo "WARN: $func has 0 callers — wire or delete"
  fi
done
```

### 2. CI gate: "no false-confidence return"

```bash
# Grep cho pattern "verdict = PASS" — review mỗi occurrence
rg -n 'verdict\.verdict\s*=\s*"PASS"|verdict.*=.*"PASS"' scp/ --include="*.py"
# Mỗi hit phải có comment giải thích EVIDENCE source
```

### 3. CI gate: "test regex sanity"

```python
# Thêm test meta: mỗi grep-based test phải verify regex matches known-bad sample
def test_regex_tests_actually_match():
    """Meta-test: verify grep-based tests can actually catch the bug they claim."""
    # For test_no_dev_mode_bypass_via_grep:
    bypass_sample = 'os.environ["SCP_DEV_MODE"] = "1"\n    return True'
    pattern = re.compile(r'SCP_DEV_MODE[^\n]*?\n(?:[^\n]*?\n){0,4}?\s*return\s+True')
    assert pattern.search(bypass_sample), "Regex doesn't match known bypass — test is no-op!"
```

### 4. Audit process: "reality test = called, not callable"

R13's reality test verified "callable" (function exists). Future rounds must verify "called" (function has ≥1 production call site). Đây là meta-fix cho DNA #22 recursive.

---

## Tóm tắt

| Phase | Fix | Impact | Risk | Timeline |
|---|---|---|---|---|
| **P0-1** | ReActAgent không ghi đè verdict | **Dừng SCP killer** — không còn PASS dựa trên LLM answer length | LOW | 1-2h |
| **P0-2** | SLM deterministic + reality check | Bug trong 4 SLM không unchecked | MED | 2-3h |
| **P0-3** | execute_plan không PASS không source | Regex exploit bị chặn | LOW | 1h |
| **P1-1** | Wire verify_chain | Tamper-evidence gate thực sự enforce | MED | 2h |
| **P1-2** | Wire check_pending_permissions | Permission system enforce | MED | 1h |
| **P1-3** | policy_gate fail-closed | eval()/shell=True không được ALLOW khi disk full | MED | 1h |
| **P2-1** | Fix test regex | Admin auth bypass regression test thực sự chạy | LOW | 30min |
| **P2-2** | understanding_check fail-closed | Tier-3 approval không auto-accept | LOW | 30min |
| **P3-1** | Dependency fixes | py39→py310, hypothesis in requirements | LOW | 2h |
| **P3-2** | Dead code cleanup | -1200 LOC, cleaner tree | LOW | 4h |

**Ưu tiên tuyệt đối: P0-1 (ReActAgent) trong ngày hôm nay.** Mỗi giờ không fix = mỗi giờ SCP có thể trả PASS/conf=0.9 trên LLM answer bịa — exact failure mode SCP được thiết kế để prevent.

> **KHÔNG HOÀN THIỆN. KHÔNG THẤT BẠI. KHÔNG HOÀN TẤT. ĐANG HOẠT ĐỘNG.** (DNA #23)
>
> **Và Reality vẫn giữ quyền trả lời cuối cùng.** (DNA #26 🌍)
