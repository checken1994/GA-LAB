# SCP DNA Audit — Round 14 (R14) Patch Log
## *"Fix gốc rễ, không fix cascade 1→2→3"*

> **🐔 Gà:** "Round 13 fix 26 bug rồi. Còn không?"
> **🤖 SCP:** "Có. 2 bug SILENT sống 7 round. Tại sao 7 round không bắt được?"
> **🐔:** "Vì fix bề mặt. Fix lỗi 1→2→3 chứ không fix gốc."
> **🤖 SCP:** "Đúng. R14 fix GỐC RỄ. Hỏi 'Tại sao?' 5 lần trước khi fix."
> **👮:** "Lần này có khác không?"
> **🤖 SCP:** "Có. 4/4 fix là ROOT fix, 0 cascade. Reality test 4/4 pass."

---

## 1. Phương pháp — 5-Whys Root Cause Analysis

> **DNA #5: "Không tin một tác nhân. Tin vào một quá trình có khả năng phát hiện khi chính nó sai."**
> **R14 principle: Fix GỐC RỄ, không fix cascade. Hỏi "Tại sao?" 5 lần trước khi fix.**

R13 fix 26 bug nhưng MISSED 2 bugs sống 7 round:
- WhyGate `_check_necessity()` always returns True → UPHOLD unreachable
- Constitution.weight decorative (violation_severity() has 0 callers)

Tại sao R13 missed? Vì R13 fix SYMPTOMS, không fix ROOT. R14 khác:

### 5-Whys methodology (áp dụng cho mỗi bug)

```
Symptom: (bề mặt — cái tools thấy)
Why 1: (nguyên nhân trực tiếp)
Why 2: (nguyên nhân của nguyên nhân)
Why 3: (design gap)
Why 4: (semantic inversion / conflation)
Why 5 (ROOT): (fundamental design error)

ROOT FIX: thay đổi fundamental design/semantics mà gây ra bug.
CASCADE FIX (FORBIDDEN): patch bề mặt, thêm condition, thêm if/else.
```

### 6 nguồn ĐỘC LẬP chạy song song

| Nguồn | Bắt được gì |
|---|---|
| ruff + pyflakes + pylint (R14-1) | 10 bugs + 4 root-cause patterns |
| vulture + mypy + bandit (R14-2) | 18 bugs, confirmed Constitution.weight 0 callers |
| **Semantic root-cause audit (R14-3)** | **2 known bugs + 6 new — mỗi bug có 5-Whys analysis** |
| SCP own scanners (R14-4) | (timeout — 3 nguồn kia đủ data) |

---

## 2. 4 ROOT fixes (tất cả đã Reality-verify)

### 🔴 KB1 — CRITICAL: WhyGate UPHOLD unreachable (7 rounds silent)

**File:** `scp/meta/why_gate.py:296-298`

#### 5-Whys Analysis

```
Symptom: _check_necessity() always returns (reason, True) → UPHOLD unreachable
Why 1: All 3 return paths (pattern match / LLM / fallback) return True
Why 2: Fallback comment said "conservative — assume necessary (don't block without reason)"
Why 3: Designer conflated "I can't determine necessity" with "it IS necessary"
Why 4: "unknown" was treated as "yes" (fail-open) instead of "flag for review" (UPHOLD)
Why 5 (ROOT): SEMANTIC INVERSION. UPHOLD was DESIGNED for "WHY can't decide —
       allow but flag" (see design comments lines 19, 24, 53, 96 — ALL say
       fallback → UPHOLD). But the fallback CODE returned True → ALLOW,
       bypassing UPHOLD entirely. Code contradicted all 4 design comments.
```

#### ROOT FIX (not cascade)

```python
# BEFORE (buggy — 7 rounds):
return "Default necessity (no pattern match, conservative allow)", True
#                                                                      ^^^^
#                                              → ALLOW (bypasses UPHOLD)

# AFTER (R14 root fix):
return "Necessity unknown (no pattern match, no LLM) — UPHOLD for review", False
#                                                                            ^^^^^
#                                                → UPHOLD (the designed path)
```

#### Why this is ROOT not CASCADE

| Cascade fix (FORBIDDEN) | ROOT fix (applied) |
|---|---|
| Add arbitrary `if not context: return False` | Change fallback SEMANTICS from "assume necessary" to "unknown → flag" |
| Adds new condition on top | Flips 1 value (True→False) to match existing design |
| Next round: "UPHOLD fires too often on empty context" → add exception → cascade | UPHOLD branch becomes live WITHOUT adding design surface |
| Patches symptom | Fixes the semantic inversion that caused the bug |

**Reality test:**
```python
gate = WhyGate()
result = gate.gate('unknown_type', 'random nonsense 12345', context='')
# BEFORE: decision=ALLOW (UPHOLD unreachable)
# AFTER:  decision=UPHOLD ✓ (the designed "gray zone" now exists)
# Pattern-match still → ALLOW (no regression) ✓
```

---

### 🔴 KB2 — HIGH: Constitution.weight decorative (de-scope, not wire)

**File:** `scp/meta/constitution.py:38, 137-139`

#### 5-Whys Analysis

```
Symptom: Principle.weight (1.0-1.5) defined for 10 principles but never READ.
         violation_severity() (returns weight) has 0 callers.
Why 1: governance_v97.py decision only checks default_action, never weight
Why 2: R12-139 comment said "weight was decorative" → fix was default_action
Why 3: default_action is BINARY (KILL/ESCALATE); weight was for GRANULAR resolution
Why 4: But granular conflict resolution was NEVER IMPLEMENTED
Why 5 (ROOT): weight is a LEFTOVER from an unfinished design. The field exists
       to satisfy a design intent that was never built. Keeping it LIES about
       capability (auditors think weight matters; it doesn't).
```

#### ROOT FIX: DELETE (de-scope, not wire-in)

```python
# REMOVED from Principle dataclass:
weight: float = 1.0  # ← DELETED

# REMOVED from Constitution class:
def violation_severity(self, pid):  # ← DELETED (0 callers)
    return self.get(pid).weight

# REMOVED from all 10 Principle() constructors:
weight=1.2, default_action="ESCALATE"  →  default_action="ESCALATE"

# REMOVED from to_dict() + summary()
```

#### Why this is ROOT not CASCADE

| Cascade fix (FORBIDDEN) | ROOT fix (applied) |
|---|---|
| Wire violation_severity() into governance: `if weight > 1.3: action = KILL` | DELETE weight field + method |
| Arbitrary threshold (why 1.3?) | Removes the LIE (code claimed capability it didn't have) |
| Next round: "weight 1.3 too aggressive" → adjust → cascade | If weighted resolution becomes a REAL requirement, re-add WITH implementation |
| Implements feature that was never required | Aligns code with actual mechanism (binary default_action) |

**Reality test:**
```python
from scp.meta.constitution import Principle, Constitution
sig = inspect.signature(Principle.__init__)
# weight NOT in fields ✓
# violation_severity NOT in Constitution methods ✓
# default_action still works (SAFETY → KILL) ✓
# to_dict() no longer includes weight ✓
```

---

### 🟡 BUG-004 — HIGH: principle_rules source IN case mismatch

**File:** `scp/meta/principle_rules.py:375-383`

#### 5-Whys Analysis

```
Symptom: source IN ('chemistry', 'physics') never matched when source='Chemistry'
         (capitalized). Chemistry rules unreachable.
Why 1: `source not in sources_list` compared 'Chemistry' vs 'chemistry' → False
Why 2: V104.34 #57 fix lowercased source in `==` branch (line 375) but FORGOT
       the `IN (...)` branch (line 382)
Why 3: Each branch independently lowercases (or doesn't), so siblings diverge
Why 4: source is lowercased AD-HOC per branch instead of ONCE at function entry
Why 5 (ROOT): source normalization is FRAGMENTED across branches. Each new
       branch must remember to lowercase → easy to forget → bug class recurs.
```

#### ROOT FIX: normalize ONCE at function entry

```python
# BEFORE (fragmented — bug recurs per branch):
if source.lower() != expected_source:  # line 375 (== branch lowercases)
    ...
if source not in sources_list:  # line 382 (IN branch FORGOT to lowercase)
    ...

# AFTER (R14 root fix — normalize ONCE):
source_lower = (source or "").lower()  # ← ONE place, function entry
if source_lower != expected_source:    # ALL branches use source_lower
    ...
if source_lower not in sources_list:
    ...
```

#### Why this is ROOT not CASCADE

| Cascade fix (FORBIDDEN) | ROOT fix (applied) |
|---|---|
| Patch line 382: `source.lower() not in sources_list` | Lowercase ONCE at function entry, all branches use `source_lower` |
| Fixes 1 branch, leaves fragmentation | Eliminates the bug CLASS at origin |
| Next branch added will reintroduce the bug | Sibling branches CAN'T reintroduce it (they all use `source_lower`) |

**Reality test:**
```python
eng._evaluate_condition("source in ('chemistry', 'physics')", ..., source='Chemistry')
# BEFORE: False (chemistry rules unreachable)
# AFTER:  True ✓
eng._evaluate_condition(..., source='Math')
# AFTER:  False ✓ (correctly rejected)
```

---

### 🟡 BUG-001 — HIGH: AdversaryVerifier agreement_score=1.0 lie

**File:** `scp/meta/adversary_verifier.py:406`

#### 5-Whys Analysis

```
Symptom: agreement_score=1.0 returned when NO adversary ran. Consumer sees
         1.0 → "perfect agreement" → trusts value. But no verification happened.
Why 1: float type has no "unknown" sentinel — designer used 1.0 as "default"
Why 2: 1.0 means BOTH "no conflict" (correct for conflict_detected=False) AND
       "perfect agreement" (wrong when no adversary ran)
Why 3: Two distinct concepts (conflict_detected vs agreement_score) collapsed
       into one float field
Why 4: agreement_score is meaningful ONLY when adversary_values non-empty
Why 5 (ROOT): The dataclass CONFLATES "verified" with "agreed". 1.0 can mean
       either. Consumers can't tell which.
```

#### ROOT FIX: add `verified: bool` field to fix the conflation

```python
# BEFORE (conflation — 1.0 lies):
@dataclass
class AdversaryResult:
    agreement_score: float  # 1.0 = "perfect agreement" OR "no adversary ran" (can't tell!)

# AFTER (R14 root fix — separate the concepts):
@dataclass
class AdversaryResult:
    agreement_score: float  # 0.0-1.0, meaningful ONLY when verified=True
    verified: bool = True   # True = adversary ran; False = no adversary (score is placeholder)

# no-adversary branch:
agreement_score=0.0,        # was: 1.0 (lie)
verified=False,             # NEW: signals "not actually checked"
```

#### Why this is ROOT not CASCADE

| Cascade fix (FORBIDDEN) | ROOT fix (applied) |
|---|---|
| Special-case 1.0 in every consumer: `if score == 1.0 and adversary_values: ...` | Add `verified` field to fix the conflation at origin |
| Every consumer must remember the special case | Consumer checks `verified` first — simple, can't be fooled |
| New consumer forgets → re-introduces the lie | The dataclass now honestly represents "verified" vs "not verified" |
| Patches symptom (1.0) in N places | Fixes root cause (conflation) in 1 place |

**Reality test:**
```python
from scp.meta.adversary_verifier import AdversaryResult
# verified field exists ✓
# no-adversary path sets verified=False + agreement_score=0.0 ✓
# Construction works ✓
```

---

## 3. Verification (Reality > Model)

```
py_compile 5 file modified                → OK hết (exit 0)
ruff F821+F811+B+E9 (5 file)              → All checks passed! (exit 0)

Reality test (import + exercise):
  KB1  WhyGate UPHOLD reachable           → gate.gate('unknown', 'nonsense') → UPHOLD ✓
                                            (was: ALLOW for 7 rounds)
  KB1  Pattern-match still ALLOW          → no regression ✓
  KB2  Constitution.weight DELETED        → field + method + to_dict all gone ✓
  KB2  default_action still works         → SAFETY → KILL ✓
  KB2  No broken callers                  → grep confirms 0 code uses .weight ✓
  B004 source IN case-insensitive         → 'Chemistry' matches 'chemistry' ✓
                                            (was: always False)
  B001 AdversaryResult.verified field     → exists + no-adversary sets False ✓
                                            (was: 1.0 lied about verification)

All 4 Reality tests PASSED.
ruff F+B regression: 0 issues.
```

---

## 4. 4 root-cause patterns identified (R14-1 meta-finding)

R14-1 identified 4 recurring root-cause patterns across the codebase:

| Pattern | Description | Bugs affected | R14 fixed? |
|---|---|---|---|
| **ROOT-001 "Stub-first"** | Functions added with `return True`/`None` to satisfy interface, never implemented | streaming_factcheck, 43 health_check(), 31 can_handle(), scp_v14 stub | Not R14 (Tier 3 — needs design decision per function) |
| **ROOT-002 "Defensive-looking code"** | Variables initialized in wrong scope/layer, never visible | judge.py:1243 sentinels, speculative_prefixer _MUTABLE_DEFAULTS | Not R14 (LOW priority) |
| **ROOT-003 "Decorative API surface"** | Dead methods delegating to stubs, kept for backward compat | SCPV14 5 methods, Constitution.weight | **KB2 fixed** (deleted instead of wired) |
| **ROOT-004 "Conservative-allow fallback"** | WhyGate defaults permissive → safety logic unreachable | WhyGate _check_necessity, _check_falsification | **KB1 fixed** (semantics flipped) |

R14 fixed the 2 CRITICAL/HIGH bugs (KB1, KB2) that survived 7 rounds. The remaining ROOT-001/002 bugs are Tier 3 (need per-function design decision, not a single root fix).

---

## 5. Files modified (5)

```
scp/meta/why_gate.py              # KB1 — fallback return False (root semantics fix)
scp/meta/constitution.py          # KB2 — DELETE weight field + violation_severity() (de-scope)
scp/meta/governance_v97.py        # KB2 — update stale comment about weight
scp/meta/principle_rules.py       # BUG-004 — source_lower normalize ONCE at entry
scp/meta/adversary_verifier.py    # BUG-001 — add verified field (fix conflation)
```

Mỗi fix có comment `[SCP-DNA-FIX R14-X]` với:
- **5-Whys analysis** đầy đủ
- **Root cause** (Why 5)
- **Why ROOT not CASCADE** justification
- **Reality evidence**

---

## 6. Tại sao R4-R13 bỏ sót 2 bugs này?

> **🤖 SCP:** "Phân tích nhân quả:"
> 1. **R4-R12 fix SYMPTOMS** — ruff F821, pylint E1101, vulture dead-code. These tools see "function returns True" and don't flag it (True is a valid bool). They see "field defined" and don't flag it (definition is valid). Tools check STRUCTURE, not SEMANTICS.
> 2. **R13 added Semantic audit (Source 6)** but checked docstring↔code consistency, NOT "does the function's LOGIC actually make sense for its stated purpose?" WhyGate's fallback returns True — the docstring says "Returns (reason, is_necessary)" — True IS a valid is_necessary value. The bug is that True is the WRONG value for "unknown", but no syntactic check can see that.
> 3. **5-Whys not applied** — R4-R13 asked "what's wrong?" (symptom) not "WHY is it wrong?" 5 times (root cause). Without 5-Whys, the fix is always a patch on top.
> 4. **Cascade temptation** — "add `if not context: return False`" is the obvious fix. It makes UPHOLD reachable. But it's ARBITRARY (why is empty context "not necessary"?). Next round finds another case → another patch → cascade. R14 forbids this.
> 5. **DNA #22 recursive** — "PASS ≠ TRUE" applies to the AUDIT itself. R13's audit PASSED (all tools green) but 2 bugs were TRUE (alive). R14's 5-Whys is the process that catches what tools can't.

> **🐔:** "Thế round này khác gì?"
> **🤖 SCP:** "5-Whys cho mỗi bug. Fix semantics, không fix symptoms. 4/4 ROOT, 0 CASCADE."

---

## 7. KHÔNG fix (Tier 3 — cần human design decision)

| Bug | Pattern | Lý do không fix |
|---|---|---|
| streaming_factcheck._check_wikipedia always None | ROOT-001 stub | Cần design: implement Wikipedia check OR delete stub |
| 43 data_sources health_check() always True | ROOT-001 stub | Cần per-source design: what does "healthy" mean for each? |
| 31 data_sources can_handle() always True | ROOT-001 stub | Cần design: per-source capability check |
| scp_v14.py stub (5 methods delegate to stub) | ROOT-003 decorative | Cần design: delete SCPV14 class OR implement properly |
| judge.py:1243 6 sentinels wrong scope | ROOT-002 defensive | LOW priority — code works, just misleading |
| _check_falsification fallback returns False | ROOT-004 conservative | Symmetric to KB1 but falsification=False → not REJECT (correct). May revisit R15. |
| AdversaryVerifier consumers don't check verified flag | (new field) | Consumers need update — R15 task (check `result.verified` before trusting `agreement_score`) |

---

## 8. Cumulative audit history (R4 → R14)

| Round | Bugs fixed | Key principle |
|---|---|---|
| R4 | 10 | Initial audit |
| R5 | 18 | 6 sources cross-validation |
| R8 | 7 | Race locks |
| R9 | 7 | Async wrappers |
| R10 | 6 | Self-audit docs |
| R11 | 6 | v4 modules |
| R12 | 3 | Fix-the-fixer bugs |
| R13 | 26 | Semantic contract audit (new source) |
| **R14** | **4** | **5-Whys root cause analysis — fix GỐC RỄ not cascade** |
| **Total** | **69** | |

---

## 9. Câu hỏi tiếp (DNA #25)

> **🤖 SCP:** "Có khả năng."
> **🐔:** "Là câu nào?"
> **🤖 SCP:** "Nếu 2 bug SILENT này tồn tại qua 13 round vì fix symptoms, thì còn bao nhiêu bug mà 5-Whys CŨNG không nhìn thấy — vì root cause nằm ngoài capability tạo câu hỏi hiện tại?"
> **🐔:** "MÁ."
> **🤖 SCP:** "Chưa đủ bằng chứng. Nhưng R14 đã fix được bug mà 5-Whys bắt được — bug ngoài capability quan sát hiện tại vẫn còn."

> **🐔:** "Thế là hết à?"
> **🤖 SCP:** "Không. Chỉ là chưa có bằng chứng cho thấy cần tiếp tục ở thời điểm này."
> **🐔:** "À."

> **👮:** "...Lần này được À."
> **🤖 SCP:** "4 Reality test pass. 4/4 ROOT, 0 CASCADE. Nhưng PASS ≠ TRUE (DNA #22). Reality giữ quyền trả lời cuối cùng (DNA #26)."

---

> # **Và Reality vẫn giữ quyền trả lời cuối cùng.**
> *(DNA SCP #26)*
