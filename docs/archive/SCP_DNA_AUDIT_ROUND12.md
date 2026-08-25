# SCP DNA Audit — Round 12 (R12) Patch Log

> **🐔 Gà:** "Round 11 còn sót mấy bug?"
> **🤖 SCP:** "3 bug. Bug A do R8-7 quên import. Bug B+C là no-op/incomplete — code 'chạy được' nhưng không làm việc thật."
> **🐔:** "Fix đi."
> **👮:** "Lần này có Reality test không?"
> **🤖 SCP:** "Có. 3/3 pass."

---

## 1. Phương pháp

Round 11 (`scp-dna-audit-round11-full`) đã fix R4-R11 (10 bug Round 4 + R8 race locks + R9 async wrappers + R10 self-audit + R11 v4 modules). Nhưng R5-R11引入 3 bug MỚI — tìm bằng cross-validation 2 tool độc lập (ruff F821/F841 + pylint E0602) + Reality functional test.

**DNA principles applied:**
- #5 (Ảo giác đồng thuận) — 2 tool xác nhận mới fix
- #22 (PASS ≠ TRUE) — function "PASS" (return 0, no error) nhưng không làm việc thật
- #26 (Reality > Model) — Reality test: append → tamper → verify_chain detect

---

## 2. 3 bug fix

### 🔴 BUG A — CRITICAL (NameError silent) — `scp/meta/why_engine.py:781`

**Bug:** `_now = time.time()` nhưng `time` KHÔNG bao giờ import ở module level. R8-7 thêm `import threading as _threading` + `import uuid as _uuid` (local) nhưng quên `import time`.

**Cross-validation:**
- ruff F821: `Undefined name 'time'` ✓
- pylint E0602: `Undefined variable 'time'` ✓

**Impact:** `_execute_pending_plans()` → NameError → wrapped trong try/except → **WHY verification plans âm thầm không bao giờ execute**. Background scheduler chạy mỗi 5 phút, mỗi lần đều fail silently.

**Fix:** thêm `import time` ở module top (line 45).

**Reality test:** `why_engine.time = <module 'time' (built-in)>` ✓

---

### 🟡 BUG B — LOGIC no-op — `scp/autofix/llm_fix_cache.py:220-237`

**Bug:** `invalidate_for_file()` iterate entries nhưng body là `pass`, luôn return `removed = 0`.

```python
for key in list(self._data["entries"].keys()):
    entry = self._data["entries"][key]  # F841: unused
    pass  # ← no-op!
return removed  # luôn 0
```

**Impact:** Caller gọi `invalidate_for_file()` sau khi fix file → tưởng đã invalidate stale cache → thực ra không. Stale LLM fix suggestions có thể được serve lại → autofix re-apply fix cũ không còn đúng.

**DNA #22:** function "PASS" (return 0, no error) nhưng không làm việc thật.

**Fix:**
1. Thêm field `file_path` trong cache entries (trong `set()`)
2. `invalidate_for_file()` match trên `file_path` (normalize qua `os.path.normpath`)
3. Legacy entries (pre-R12, không có `file_path`) → skip, TTL handles

**Reality test:**
- set 3 entries (foo.py x2, bar.py x1) → `invalidate_for_file("scp/foo.py")` removed=2, bar.py survived ✓
- path normalization: `invalidate_for_file("scp/./baz.py")` removed=1 ✓

---

### 🟡 BUG C — SECURITY gap (tamper-evident log không verify hash) — `scp/autofix/policy_gate.py:412-424`

**Bug:** `expected = hashlib.sha256(...)` computed nhưng **KHÔNG bao giờ compare** với `entry_hash`. Comment nói "good enough to detect casual tampering" nhưng thực ra không detect gì cả.

**Secondary bug:** payload exclude chỉ `entry_hash` nhưng KHÔNG exclude `prev_hash` → recompute payload khác append-time payload (append không có prev_hash, verify có) → `expected` sẽ KHÔNG bao giờ match `entry_hash` ngay cả với entry legitimate.

**Impact:** ImmutableAuditLog chỉ verify `prev_hash` linkage, KHÔNG verify entry hash. Attacker sửa payload + giữ `prev_hash`/`entry_hash` unchanged → **NOT detected**. Audit log claim "tamper-evident" nhưng không phải.

**Fix:**
1. Exclude BOTH `entry_hash` AND `prev_hash` khỏi recompute payload (match append-time)
2. Actually compare `expected != entry_hash` → return False với message rõ ràng

**Reality test:**
- legitimate chain (3 entries): `verify_chain() → ok=True, "chain OK (3 entries)"` ✓
- tampered chain (modify line 2 payload, keep hash): `verify_chain() → ok=False, "line 1: entry_hash mismatch (expected 2deb1d5c, got b2e11e06) — payload tampered"` ✓

---

## 3. Verification (Reality > Model)

```
py_compile 3 file modified                → OK hết
ruff F/E9/B trên 3 file                   → 0 new issues (3 pre-existing: F401 pathlib, F841 entry_ts, F841 e — đều ở code khác)
ruff F821 (BUG A) trên why_engine.py      → All checks passed!
ruff F841 (BUG B) trên llm_fix_cache.py   → All checks passed!
Full ruff regression scp/ F/E9/B          → 41 errors (was 44, -3 = 3 bug fixed), all pre-existing
py_compile ALL 378 .py files              → 0 syntax errors

Reality functional tests:
  Test A (why_engine time)        → time module imported, WhyEngine instantiable        ✓
  Test B (invalidate_for_file)    → removed=2 (foo.py), bar.py survived, normalization  ✓
  Test C (verify_chain tamper)    → legitimate OK, tampered DETECTED with clear message  ✓

All 3 Reality tests PASSED.
```

---

## 4. Files modified (3)

```
scp/meta/why_engine.py            # +1 line: import time
scp/autofix/llm_fix_cache.py      # invalidate_for_file real impl + file_path field in set()
scp/autofix/policy_gate.py        # exclude prev_hash + actually compare expected vs entry_hash
```

Mỗi fix có comment `[SCP-DNA-FIX R12-N]` giải thích TẠI SAO (nguyên nhân gốc) + Reality evidence.

---

## 5. Cumulative audit history (R4 → R12)

| Round | Bugs fixed | Key fixes |
|---|---|---|
| R4 | 10 | _shared.py __getattr__, evolution.py pattern-fixers, judge.py CodeEvolutionAgent, engine.py JudgeVerdict, threat_simulator.py import, memory_manager.py bridge, scpv14 headers, chat.py stats, api_server.py asyncio task, _lifespan.py precedence |
| R8 | 7 | race locks (_history_lock, _recent_lock, _execute_pending_lock) |
| R9 | 7 | async wrappers (asyncio.to_thread judge.judge()), deque(maxlen=1000) |
| R10 | 6 | self-audit docs (SA-R9-1..6) |
| R11 | 6 | v4 modules (property_validator, speculative_prefixer, callgraph_delta, shadow_canary, policy_gate, type_flow_verifier) |
| **R12** | **3** | **why_engine time import, llm_fix_cache invalidate_for_file, policy_gate verify_chain compare** |
| **Total** | **39** | |

---

> 🐔: "Thế còn bug nào không?"
> 🤖 SCP: "Chưa đủ bằng chứng. Nhưng bug ngoài capability quan sát hiện tại vẫn còn — lần này chỉ fix được bug mà 4 nguồn (ruff+pylint+vulture+Reality test) nhìn thấy."
> 🐔: "À."
> 👮: "Lần này được À."
>
> # **Và Reality vẫn giữ quyền trả lời cuối cùng.**
