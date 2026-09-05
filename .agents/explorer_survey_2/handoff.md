# Deep Investigation Report: FA-02 Skip Paths, Baseline Debt & Epistemic EvidenceStore Lifecycle

**Investigator**: Explorer Survey 2 (`teamwork_preview_explorer`)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_survey_2`  
**Git HEAD Snapshot**: `48e5ca8dd0867d1257103ea66f73be752d785b60` (`experts-4.0.3-434green`)  
**Applied Skills**: `scp-dna` (DNA Principles #1, #5, #14, #19, #22, #23, #26), `scp-reality-verifier` (4 evidence levels)

---

## 1. Observation

### 1.1 T00 Meta-Audit Live Execution & Reported Baseline Debt
Running `python tools/t00_meta_audit.py` against `trusted_base = origin/main` yielded exit code 0 and exposed the following verbatim findings:

```
[T00 Meta-Audit] Starting Test-Integrity Regression Authority...
[T00 Meta-Audit] Trusted Base: origin/main

--- SCOPE & LIMITATIONS ---
 * FA-01 (Semantic Weakening): Partial (skip/xfail checked, incl. module-level pytestmark). Logic weakening requires L4 human review.
 * FA-02: ENFORCED for regressions in collected pytest nodeids
 * FA-03 (Same-SHA Evidence): NOT ENFORCED by T00 (Requires dedicated evidence tool).
 * FA-04 (Manufactured Green): Regex-based. Complex AST tracking requires L4 human review.
 * FA-05 (Self-Granting Auth): NOT ENFORCED by T00 (Requires capability scanner).
[T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
[T00 Meta-Audit] Collecting candidate pytest nodeids...

--- BASELINE_DEBT (Tracked, Not Blocking) ---
 [DEBT] FA-01: scp/tests/external_audit/test_security.py -> pytest.skip() in test_bandit_no_new_high_severity_via_bandit (2 historical instances)
 [DEBT] FA-01: scp/tests/external_audit/test_security.py -> pytest.skip() in test_no_hardcoded_token_in_source (1 historical instances)
 [DEBT] FA-01: tests/T03_capability/test_os_sandbox.py -> pytest.skip() in test_sandbox_executes_command_inside_job_object (1 historical instances)
 [DEBT] FA-01: tests/T03_capability/test_os_sandbox.py -> pytest.skip() in test_sandbox_rejects_invalid_capability (1 historical instances)
 [DEBT] FA-04: scp/autofix/evidence_replay.py -> hardcoded VERIFIED: return {"ok": True, "status": "VERIFIED"} (1 historical instances)

--- L4 CODEOWNERS (Warning) ---
 [L4] L4 Protected Path Modified: .agents/ORIGINAL_REQUEST.md
 [L4] L4 Protected Path Modified: .agents/sentinel/BRIEFING.md
Note: L4 is VERIFIED only by GitHub Server-Side Ruleset. This is a local warning.

[T00 Meta-Audit] All integrity checks passed (0 new regressions).
```

### 1.2 Direct Observation of FA-02 Skips and Bypasses in Code

#### A. `tests/T03_capability/test_os_sandbox.py` (Lines 8–29)
```python
8: def test_sandbox_executes_command_inside_job_object():
9:     if platform.system() != "Windows":
10:         pytest.skip("Job Object sandbox is Windows-specific")
...
20: def test_sandbox_rejects_invalid_capability():
21:     if platform.system() != "Windows":
22:         pytest.skip("Job Object sandbox is Windows-specific")
```
- **Observed Behavior**: On non-Windows OS (Linux GitHub runners, macOS), the entire process isolation boundary skips silently, passing the suite without checking if unisolated processes are executed or failed-closed.

#### B. `scp/tests/external_audit/test_security.py` (Lines 112–157)
```python
112: def test_no_hardcoded_token_in_source():
113:     """RC-2 CODE-AUDIT-001: no production token hardcoded in source."""
114:     token = os.environ.get("SCP_AUTH_TOKEN_SECRET", "")
115:     if not token:
116:         pytest.skip("SCP_AUTH_TOKEN_SECRET not set — cannot verify no-hardcoded-token")
...
145: def test_bandit_no_new_high_severity_via_bandit():
146:     """RC-10 external audit: bandit HIGH-severity count must not increase."""
147:     result = safe_run(["bandit", "-r", str(SCP_ROOT), "-f", "json", "-q"])
150:     if result.returncode not in (0, 1):
151:         pytest.skip(f"bandit failed to run: {result.stderr[:200]}")
153:     try:
154:         data = json.loads(result.stdout)
155:     except json.JSONDecodeError:
156:         pytest.skip("bandit did not produce JSON output")
```
- **Live Terminal Execution**: `python -m pytest scp/tests/external_audit/ -rs` produced:
```
scp\tests\external_audit\test_security.py ..ss.......                    [100%]

=========================== short test summary info ===========================
SKIPPED [1] scp\tests\external_audit\test_security.py:116: SCP_AUTH_TOKEN_SECRET not set — cannot verify no-hardcoded-token
SKIPPED [1] scp\tests\external_audit\test_security.py: bandit not installed
======================== 9 passed, 2 skipped in 0.76s =========================
```
Exit code was `0`. The test suite claimed "9 passed" while skipping the security token check and bandit security scan.

#### C. `scp/tests/external_audit/conftest.py` (Lines 25–35) — Dynamic Hook Bypass
```python
25: def pytest_collection_modifyitems(config, items):
26:     """Mark tests that need external tools — skip if tool missing."""
27:     for item in items:
28:         if "via_ruff" in item.nodeid and shutil.which("ruff") is None:
29:             item.add_marker(pytest.mark.skip(reason="ruff not installed"))
30:         if "via_bandit" in item.nodeid and shutil.which("bandit") is None:
31:             item.add_marker(pytest.mark.skip(reason="bandit not installed"))
32:         if "via_grep" in item.nodeid and shutil.which("grep") is None:
33:             item.add_marker(pytest.mark.skip(reason="grep not installed"))
```
- **AST Scanner Blind Spot**: `t00_meta_audit.py` inspects `@pytest.mark.*` decorators and `pytest.skip()` calls, but does NOT inspect pytest collection hook methods (`pytest_collection_modifyitems`). Consequently, dynamic skips injected at collection time evade T00 AST auditing.

#### D. `scp/tests/property/test_none_safety.py` (Lines 77–227) — Variable Aliasing Bypass
```python
77: _HYPOTHESIS_SKIP = pytest.mark.skipif(
78:     not HAS_HYPOTHESIS, reason="hypothesis not installed (install with: pip install hypothesis)"
79: )
...
112: @_HYPOTHESIS_SKIP
113: @given(...)
114: def test_crypto_guard_never_raises(value): ...
...
216: @_HYPOTHESIS_SKIP
217: @pytest.mark.parametrize("label,value,expected", [...])
218: def test_r7_1_documented_cases(label, value, expected): ...
```
- **AST Blind Spot**: `AuditVisitor._handle_function` in `tools/t00_meta_audit.py` checks `attr_name in ('skip', 'xfail', 'skipif')`. Because the decorator is referenced via variable `_HYPOTHESIS_SKIP` (an `ast.Name` node with `id='_HYPOTHESIS_SKIP'`), it does not match `'skipif'`, escaping T00 AST detection.
- **Over-skipping**: `test_r7_1_documented_cases` does NOT use Hypothesis, yet is decorated with `@_HYPOTHESIS_SKIP`. If `hypothesis` is uninstalled, deterministic smoke tests are skipped unnecessarily.

#### E. `tests/reality-tests/*.py` — Broad Exception Catch-and-Pass
Across 20+ standalone reality scripts (e.g., `reality_4-a-002.py:106-116`, `reality_4-a-004.py:160-175`, `reality_4-a-005.py:245`, `reality_4-a-006.py:261`, `reality_4-a-010.py:91-113`), the following construct is used:
```python
# From reality_4-a-004.py:
except Exception as _e:
    _err_type = type(_e).__name__
    _err_msg = str(_e)[:150]
    print(f"SKIP [3/3]: runtime test skipped — exception during execution (DNA #23: honest limit)")
    print("\n✓ Reality test 4-a-004 PASSED (2/3 assertions run, 1 skipped — honest limit DNA #23)")
```
- **Observed Behavior**: The script traps ANY unhandled exception during dynamic execution, prints `SKIP`, prints `✓ Reality test ... PASSED`, and exits with code 0. A fatal runtime failure is converted into a green test run.

#### F. `scp/autofix/runner_phases/reality_test.py` (Lines 212–221) — Partial Callable Green
```python
204:     if callables_exercised == 0:
205:         return {"ok": False, "status": "UNVERIFIED", "reason": "0 callables exercised successfully", ...}
212:     return {
213:         "ok": True,
214:         "status": "VERIFIED",
215:         "reason": f"reality test passed, exercised {callables_exercised} callables" + ...
219:         "callables_exercised": callables_exercised,
220:         "exceptions": exceptions,
221:     }
```
- **Observed Behavior**: If `callables_exercised >= 1`, the module verdict is `VERIFIED`, even if multiple other callables raised exceptions (stored in `exceptions` but ignored for `ok: True`). Furthermore, `_build_mock_args` generates synthetic dummy values (`"test"`, `1`, `True`, `{}`, `[]`), which do not validate realistic runtime behavior.

#### G. `scp/autofix/evidence_replay.py` (Lines 28–42) — Hardcoded VERIFIED Stub
```python
28:     def verify(self, *args, **kwargs):
29:         return {"ok": True, "status": "VERIFIED"}
31:     def classify_evidence(self, *args, **kwargs):
32:         class MockResult:
33:             role = EvidenceRole.VERIFIER
...
41: def compute_bug_signature(*args, **kwargs):
42:     return "mock_signature"
```
- Flagged by `t00_meta_audit.py` as `FA-04: scp/autofix/evidence_replay.py -> hardcoded VERIFIED: return {"ok": True, "status": "VERIFIED"}`.

#### H. `tests/reality-check.sh` (Lines 405–453) — Tier B Skipped by Default
```bash
405: echo "ℹ️  Tier B (runtime) skipped. Run with --runtime to probe live services."
...
415: RT_PASS=0; RT_FAIL=0; RT_SKIP=0
...
453: echo "▶ TOTAL: $((PASS + RT_PASS)) passed, $((FAIL + RT_FAIL)) failed, $RT_SKIP skipped"
```
- Runtime daemon and network checks are skipped by default, reporting zero failures.

---

### 1.3 Epistemic EvidenceStore Architecture & Lifecycle

#### Code Locations
- Core Implementation: `scp/epistemic/evidence_store.py` (Lines 187–432)
- Persistence Authority: `scp/persistence/db.py` (`FoundationDB`, lines 37–109)
- Governance & Bridge: `scp/epistemic/evidence_writer.py`, `scp/epistemic/runtime_bridge.py`
- Unit/Integrity Tests: `tests/T06_verifier/test_evidence_store.py` (18 test cases, all passing)

#### Key Observed Lifecycle Mechanisms
1. **Schema Immutability Triggers**:
   - `0001_evidence_core`: `BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT, 'evidence is immutable - supersede instead'); END;`
   - `0002_evidence_append_only`: `BEFORE DELETE ON evidence / content_blobs / evidence_links BEGIN SELECT RAISE(ABORT, ...); END;`
   - Lifecycle tables (`evidence_payload_state`, `retention_events`) remain intentionally mutable for purge/audit state.
2. **Crash-Ordered Staging and Write Barrier (`observe`)**:
   - Lines 246–251:
     ```python
     staging = self.objects_dir / ".staging" / uuid.uuid4().hex
     staging.parent.mkdir(parents=True, exist_ok=True)
     staging.write_bytes(bytes(content))
     with staging.open("rb+") as handle:
         handle.flush()
         os.fsync(handle.fileno())
     ```
   - Deduplication check (Lines 252–257): If `blob_path.exists()`, validates `content_id(blob_path.read_bytes()) == digest`. If mismatch, raises `EvidenceIntegrityError`; if match, unlinks `staging`.
   - Atomic Rename (Lines 258–260): `os.replace(staging, blob_path)`.
   - SQLite Transaction (Lines 285–305):
     ```python
     with self.db.transaction() as conn:
         conn.execute("INSERT OR IGNORE INTO content_blobs ...")
         conn.execute("INSERT INTO evidence ...", row)
         conn.execute("INSERT INTO evidence_payload_state ... VALUES (?, 'AVAILABLE', ?)")
     ```
3. **Startup Staging Reconcile (`__init__`)**:
   - Lines 204–209:
     ```python
     staging = self.objects_dir / ".staging"
     staging.mkdir(parents=True, exist_ok=True)
     for leftover in staging.iterdir():
         leftover.unlink(missing_ok=True)
     ```
4. **Integrity Verification (`verify_integrity`)**:
   - Checks `record_hash` (either HMAC-SHA256 or SHA256) over canonical JSON metadata (`_IMMUTABLE_FIELDS`).
   - Checks `payload_state == 'AVAILABLE'`.
   - Checks `blob_path.is_file()` (fails closed if missing).
   - Checks `content_id(blob_path.read_bytes()) == record["content_hash"]` (fails closed if hash mismatch).
   - If errors detected: updates `evidence_payload_state` to `MISSING`.

---

## 2. Logic Chain

### 2.1 Causal Chain 1: FA-02 Skip Paths & Baseline Technical Debt

```
[Trigger / Input]
  ├─ Non-Windows OS detected (platform.system() != "Windows")
  ├─ Environment secret missing (SCP_AUTH_TOKEN_SECRET unset)
  ├─ External binary absent on host PATH (bandit / ruff / grep not found)
  ├─ Hypothesis library absent (HAS_HYPOTHESIS is False)
  ├─ Reality script hits missing dependency or runtime exception
  └─ Autofix reality_test hits exceptions on subset of module callables
         │
         ▼
[Test Execution & Interception]
  ├─ tests/T03_capability/test_os_sandbox.py: lines 9, 21 branch to pytest.skip()
  ├─ scp/tests/external_audit/test_security.py: line 116, 151, 156 invoke pytest.skip()
  ├─ scp/tests/external_audit/conftest.py: pytest_collection_modifyitems injects pytest.mark.skip
  ├─ scp/tests/property/test_none_safety.py: @_HYPOTHESIS_SKIP marks tests
  ├─ tests/reality-tests/*.py: except Exception catches crash and executes print("✓ ... PASSED")
  └─ scp/autofix/runner_phases/reality_test.py: filters exceptions into list, checks callables_exercised >= 1
         │
         ▼
[Bypass / Skip Encountered]
  ├─ Test execution aborted before assertion evaluation
  ├─ Exit code remains 0 (Pytest reports 'SKIPPED' as non-failing; reality scripts exit 0)
  └─ AST audit in t00_meta_audit.py is evaded by:
       • Dynamic marker injection in hooks (item.add_marker)
       • Variable aliasing (_HYPOTHESIS_SKIP)
       • Standalone script format (not recognized as pytest file)
         │
         ▼
[Technical Debt Masking]
  ├─ T00 Meta-Audit records historical skip instances as non-blocking BASELINE_DEBT
  ├─ OS Sandbox enforcement on Linux remains unverified
  ├─ Hardcoded secret presence in codebase is never scanned in standard CI
  ├─ Bandit static analysis security vulnerabilities remain undetected
  └─ Standalone reality tests conceal runtime crashes ("tĩnh sống -> thực tế chết")
         │
         ▼
[False Green / Silenced Failure]
  CI runner prints "100% passed", exit code 0.
  System is declared intact, while underlying security, isolation, and runtime execution guarantees are unproven.
```

### 2.2 Causal Chain 2: Epistemic EvidenceStore Lifecycle

```
[Event / Observation Trigger]
  Subsystem (Runtime Bridge, Gateway, Alert Router) produces observation payload (content: bytes, metadata).
         │
         ▼
[Atomic Staging Phase]
  Digest computed: digest = content_id(content)
  File path resolved: objects/sha256/xx/yy/<digest>
  Payload written to isolated staging path: .staging/<uuid>
         │
         ▼
[Flush / Write Barrier (fsync)]
  handle.flush() flushes userspace buffer to OS kernel
  os.fsync(handle.fileno()) forces physical write barrier to disk platter/NAND
  Deduplication check:
    • If blob already exists and matches hash: unlink staging file (no duplicate write)
    • If blob does not exist: os.replace(staging, blob_path) (atomic directory entry swap)
         │
         ▼
[Crash Boundary & Failure Analysis]
  ├─ Crash Boundary A (during staging write):
  │    File in .staging/<uuid>. On restart, __init__ deletes it. DB has no row. (Clean)
  │
  ├─ Crash Boundary B (after os.replace, before DB transaction commit):
  │    Blob exists on disk under content-addressed path, but DB transaction is NOT committed.
  │    -> LEAK: Blob becomes an unreferenced ORPHAN on disk.
  │    -> RECONCILIATION GAP: EvidenceStore.__init__ only cleans .staging, NOT orphans.
  │       Orphan persists until manual scan_orphans() is invoked.
  │
  ├─ Crash Boundary C (POSIX directory metadata ordering):
  │    os.replace updates directory entries. On POSIX without directory fsync (fsync on parent dir),
  │    power loss can write SQLite WAL while directory inode is lost, leaving DB with record
  │    but missing blob.
  │
  └─ Crash Boundary D (Multi-process Race Condition in __init__):
       Process 1 is writing .staging/<uuid1>.
       Process 2 starts, runs __init__, and executes `for leftover in staging.iterdir(): unlink()`.
       Process 2 DELETES Process 1's active in-flight staging file, causing Process 1 crash!
         │
         ▼
[Journal Append (DB Transaction)]
  FoundationDB begins transaction:
    • PRAGMA foreign_keys=ON, PRAGMA journal_mode=WAL, BEGIN IMMEDIATE, threading.RLock()
    • Computes record_hash (HMAC-SHA256 if key configured; plain SHA256 if keyless)
    • Atomic insert into content_blobs, evidence, evidence_payload_state (AVAILABLE)
    • COMMIT
         │
         ▼
[Recovery / Reconcile]
  On startup:
    • FoundationDB executes PRAGMA quick_check (checks DB page integrity)
    • Validates schema migration checksums against schema_migrations table
    • Unlinks files in .staging/
         │
         ▼
[Verification (`verify_integrity`)]
  On every get() / read_content():
    • Canonical metadata re-hashed against record_hash (fails closed if tampered)
    • Checks blob_path.is_file() and content_id(blob_path.read_bytes()) == content_hash
    • If missing/corrupt: records state = 'MISSING' in evidence_payload_state and raises EvidenceIntegrityError.
```

---

## 3. Caveats

1. **Host Platform Specifics**: The audit was conducted on Windows 11 (`platform.system() == "Windows"`). Behavior of `test_os_sandbox.py` on Linux was confirmed by inspecting the source code branching logic, not by running on a live Linux kernel.
2. **Pre-commit vs. CI Scope**: `t00_meta_audit.py` is configured as a pre-commit check and CI check comparing against `trusted_base` (`origin/main`). Violations in baseline are classified as `BASELINE_DEBT` rather than build-breaking errors to prevent blocking unrelated PRs, but this permits persistent debt accumulation.
3. **Database Concurrency Scope**: `FoundationDB` utilizes `threading.RLock()` which secures multi-threaded Python access. However, multi-process concurrency relies on SQLite file locking and filesystem behavior, where staging directory cleanup lacks process isolation locks.
4. **No Code Modifications**: Per the read-only explorer mandate, no files were modified or deleted outside `.agents/explorer_survey_2`.

---

## 4. Conclusion

1. **FA-02 Skips and Technical Debt**:
   - Five baseline debt violations are actively tracked by `tools/t00_meta_audit.py` (2 in `test_security.py`, 2 in `test_os_sandbox.py`, 1 in `evidence_replay.py`).
   - Four severe structural blind spots allow skips and false greens to escape T00 detection:
     1. Pytest hook marker injection (`conftest.py:pytest_collection_modifyitems`).
     2. Decorator variable aliasing (`_HYPOTHESIS_SKIP = pytest.mark.skipif(...)`).
     3. Standalone reality test scripts catching `except Exception` and printing `PASSED` with exit code 0.
     4. Autofix `reality_test.py` returning `VERIFIED` when at least 1 callable succeeds, ignoring all failing callables.
2. **Epistemic EvidenceStore Lifecycle**:
   - The crash-ordering design (`staging -> fsync -> atomic rename -> DB transaction`) is conceptually robust and enforces append-only SQLite triggers and SHA256/HMAC metadata tamper-detection.
   - Four concrete vulnerabilities were uncovered:
     1. **Orphan State Leak**: A crash between `os.replace` and DB commit leaves orphan blobs that are never reclaimed on startup.
     2. **Multi-process Staging Race**: `EvidenceStore.__init__` blindly unlinks all files in `.staging/`, which can delete in-flight staging blobs of concurrent worker processes.
     3. **POSIX Directory Sync Gap**: Missing `fsync` on directory inodes leaves directory entry changes vulnerable to power loss on ext4/xfs filesystems.
     4. **Locking Inconsistency**: `self.db._conn.commit()` is called outside the thread lock in `verify_integrity()`.

---

## 5. Verification Method

To independently verify these findings, execute the following commands on the current repository snapshot:

```powershell
# 1. Verify T00 Meta-Audit baseline debt report
python tools/t00_meta_audit.py

# 2. Verify external audit test skip behavior (observing 2 skipped tests with exit code 0)
python -m pytest scp/tests/external_audit/ -rs

# 3. Verify Epistemic EvidenceStore crash recovery and tamper detection test suite (18 passed)
python -m pytest tests/T06_verifier/test_evidence_store.py -v

# 4. Inspect conftest dynamic collection hook
view_file scp/tests/external_audit/conftest.py (lines 25-35)

# 5. Inspect EvidenceStore atomic staging and initialization
view_file scp/epistemic/evidence_store.py (lines 204-209, 244-261)
```
