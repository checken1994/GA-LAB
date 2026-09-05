# Handoff Report: Dynamic Runtime Execution Audit & Causal Chain Analysis

- **Agent**: Worker Dynamic Execution 1
- **Role**: Dynamic Runtime Execution Specialist (`implementer`, `qa`, `specialist`)
- **Working Directory**: `c:\Users\check\Downloads\scp\.agents\worker_dynamic_execution_1`
- **Snapshot Tested**: Git HEAD `48e5ca8dd0867d1257103ea66f73be752d785b60`
- **Host OS**: Windows 11 (win32) / Python 3.12.10
- **Execution Date**: 2026-09-05T17:38:00+07:00 (UTC: 2026-09-05T10:38:00Z)

---

## 1. Observation

### 1.1 `python tools/t00_meta_audit.py` (Exit Code: 0)
**Command**: `python tools/t00_meta_audit.py`
**Verbatim Output**:
```text
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

### 1.2 `python tools/verify_scp_test_skill_contract.py` (Exit Code: 0)
**Command**: `python tools/verify_scp_test_skill_contract.py`
**Verbatim Output**:
```json
{
  "commit": "48e5ca8dd0867d1257103ea66f73be752d785b60",
  "dna_principle_count": 29,
  "errors": [],
  "gate_bindings": [
    {
      "dna": [5, 14, 19, 22, 26],
      "id": "acceptance",
      "required_skills": [
        "scp-dna",
        "scp-release-evidence-gate",
        "scp-reality-verifier"
      ]
    },
    {
      "dna": [6, 19, 22, 26, 28],
      "id": "bandit_security",
      "required_skills": [
        "scp-dna",
        "scp-capability-security-review"
      ]
    },
    {
      "dna": [12, 17, 18, 19, 22, 26],
      "id": "bounded_runtime_smoke",
      "required_skills": [
        "scp-dna",
        "scp-runtime-audit",
        "scp-reality-verifier"
      ]
    },
    {
      "dna": [2, 19, 22, 26],
      "id": "compile_import",
      "required_skills": [
        "scp-dna",
        "scp-startup-troubleshooter"
      ]
    },
    {
      "dna": [2, 19, 22, 26],
      "id": "dashboard_build_audit",
      "required_skills": [
        "scp-dna",
        "scp-runtime-audit"
      ]
    },
    {
      "dna": [6, 16, 19, 22, 26, 28],
      "id": "fail_closed",
      "required_skills": [
        "scp-dna",
        "scp-capability-security-review"
      ]
    },
    {
      "dna": [8, 19, 22, 26, 28],
      "id": "manifest_provenance",
      "required_skills": [
        "scp-dna",
        "scp-release-evidence-gate"
      ]
    },
    {
      "dna": [3, 19, 21, 22, 26],
      "id": "mutation",
      "required_skills": [
        "scp-dna",
        "scp-reality-verifier"
      ]
    },
    {
      "dna": [5, 14, 16, 19, 22, 26],
      "id": "provider_failover_timeout",
      "required_skills": [
        "scp-dna",
        "scp-gateway-resilience"
      ]
    },
    {
      "dna": [5, 19, 20, 22, 25, 26],
      "id": "reality_tests",
      "required_skills": [
        "scp-dna",
        "scp-reality-verifier"
      ]
    },
    {
      "dna": [5, 14, 19, 22, 26],
      "id": "semantic_parity",
      "required_skills": [
        "scp-dna",
        "scp-runtime-audit"
      ]
    },
    {
      "dna": [3, 19, 21, 22, 25, 26],
      "id": "skill_scp_dna_contract",
      "required_skills": [
        "scp-dna",
        "scp-skill-review"
      ]
    },
    {
      "dna": [8, 17, 19, 22, 26, 28, 29],
      "id": "taskkernel_durability_recovery",
      "required_skills": [
        "scp-dna",
        "scp-task-kernel-review"
      ]
    },
    {
      "dna": [2, 5, 19, 22, 26],
      "id": "unit_integration",
      "required_skills": [
        "scp-dna",
        "scp-runtime-audit"
      ]
    }
  ],
  "handoff_gate_bindings": [
    {
      "dna": [2, 4, 8, 19, 22, 26],
      "id": "main_lineage_authority",
      "required_skills": [
        "scp-dna",
        "scp-release-evidence-gate",
        "scp-reality-verifier"
      ]
    }
  ],
  "mandatory_dna_invariants": [22, 26],
  "observed_gate_count": 14,
  "observed_handoff_gate_count": 1,
  "profile": ".agents/skills/release-gate-skill-dna-bindings.json",
  "profile_sha256": "31728d958b529bd5a86e3bb4c610d4ebc9a3405a092fd36ed7e1dc34df480bfe",
  "required_gate_count": 14,
  "required_handoff_gate_count": 1,
  "skills": {
    "scp-capability-security-review": {
      "declared_name": "scp-capability-security-review",
      "path": ".agents/skills/scp-capability-security-review/SKILL.md",
      "sha256": "83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee"
    },
    "scp-dna": {
      "declared_name": "scp-dna",
      "path": ".agents/skills/scp-dna/SKILL.md",
      "sha256": "4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10"
    },
    "scp-gateway-resilience": {
      "declared_name": "scp-gateway-resilience",
      "path": ".agents/skills/scp-gateway-resilience/SKILL.md",
      "sha256": "b60e8eb3a2d2c9de971a001924019cfa0b3038f9c96dfa4e3ac1cb8fca750a5a"
    },
    "scp-reality-verifier": {
      "declared_name": "scp-reality-verifier",
      "path": ".agents/skills/scp-reality-verifier/SKILL.md",
      "sha256": "a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e"
    },
    "scp-release-evidence-gate": {
      "declared_name": "scp-release-evidence-gate",
      "path": ".agents/skills/scp-release-evidence-gate/SKILL.md",
      "sha256": "81b2cc0e3b3be91d7780a28b5fd8a4757f05cb46fba33eab9904e056cba63ce6"
    },
    "scp-runtime-audit": {
      "declared_name": "scp-runtime-audit",
      "path": ".agents/skills/scp-runtime-audit/SKILL.md",
      "sha256": "63680fd1f1826b967f0c71367836ce0c773894f21bbf8abb33d43b005184851f"
    },
    "scp-skill-review": {
      "declared_name": "scp-skill-review",
      "path": ".agents/skills/scp-skill-review/SKILL.md",
      "sha256": "4649eb4d4a6e8c006e2db4e83b32bbe5c3f967d01a69e04e3e91a91eedf35bfa"
    },
    "scp-startup-troubleshooter": {
      "declared_name": "scp-startup-troubleshooter",
      "path": ".agents/skills/scp-startup-troubleshooter/SKILL.md",
      "sha256": "2844bf4101dc7c2df3e474ff8932dff7fba963c600a24236280564628d6a67a5"
    },
    "scp-task-kernel-review": {
      "declared_name": "scp-task-kernel-review",
      "path": ".agents/skills/scp-task-kernel-review/SKILL.md",
      "sha256": "f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334"
    }
  },
  "status": "PASS_WITHIN_SCOPE"
}
```

### 1.3 `pytest tests/` (Exit Code: 0)
**Command**: `pytest tests/`
**Result Summary**:
- Collected: 515 items
- Passed: 515 passed
- Skipped: 0
- Failed: 0
- Duration: 100.09s (0:01:40)
- Verbatim Tail:
```text
tests\contract\test_judge_verifier_contract.py .                         [ 99%]
tests\external_audit\test_cascade.py .....                               [100%]

======================= 515 passed in 100.09s (0:01:40) =======================
```

### 1.4 Full `pytest` (Default Configuration: `tests` + `scp/tests`) (Exit Code: 0)
**Command**: `pytest`
**Result Summary**:
- Collected: 548 items
- Passed: 547 passed
- Skipped: 1 (`scp/tests/external_audit/test_security.py::test_no_hardcoded_token_in_source`)
- Failed: 0
- Duration: 111.57s (0:01:51)
- Verbatim Tail:
```text
tests\contract\test_judge_verifier_contract.py .                         [ 93%]
tests\external_audit\test_cascade.py .....                               [ 93%]
scp\tests\external_audit\test_security.py ...s.......                    [ 95%]
scp\tests\property\test_none_safety.py ............                      [ 98%]
scp\tests\test_free_catalog.py ..........                                [100%]

================= 547 passed, 1 skipped in 111.57s (0:01:51) ==================
```

### 1.5 Targeted Core Subsystem Test Suites
1. **`pytest tests/T04_kernel/ -v`**:
   - Items: 22 passed in 4.39s (Exit Code: 0)
   - Verbatim: `22 passed in 4.39s`
2. **`pytest tests/T06_verifier/ -v`**:
   - Items: 50 passed in 5.85s (Exit Code: 0)
   - Verbatim: `50 passed in 5.85s`
3. **`pytest tests/T09_golden_task/ -v`**:
   - Items: 9 passed in 31.65s (Exit Code: 0)
   - Verbatim: `9 passed in 31.65s`
4. **`pytest tests/T10_recovery/ -v`**:
   - Items: 9 passed in 1.24s (Exit Code: 0)
   - Verbatim: `9 passed in 1.24s`
5. **`pytest scp/tests/ -v` vs `pytest -c pytest.ini scp/tests/ -v`**:
   - Direct execution `pytest scp/tests/ -v`:
     - Result: **FAILED** with 6 Errors in `scp\tests\test_free_catalog.py` (Exit Code: 1)
     - Verbatim Error: `PermissionError: [WinError 5] Access is denied: 'C:\\Users\\check\\AppData\\Local\\Temp\\pytest-of-check'`
     - Root Cause: Pytest uses `scp/pyproject.toml` as rootdir, which omits `addopts = --basetemp=reports/pytest-basetemp`.
   - Execution with root config `pytest -c pytest.ini scp/tests/ -v`:
     - Result: **PASSED** with 31 passed, 2 skipped in 3.22s (Exit Code: 0)

### 1.6 Direct Runtime Probes
1. **TaskKernel State Machine (18 active states vs 15 mandate)**:
   - `STATES` set in `scp/task_kernel.py:17-22`: 17 states.
   - `ALLOWED_TRANSITIONS` in `scp/task_kernel.py:24-43`: 18 states (includes `WAITING_APPROVAL`).
   - In `scp/task_kernel_parts/taskkernel.py:115` & `scp/task_kernel.py:234`:
     Explicit bypass: `if to_state not in STATES and to_state != "WAITING_APPROVAL": raise InvalidTransition(...)`
   - In `scp/task_kernel_parts/taskkernel.py:302` (`checkpoint()`):
     Un-bypassed check: `if state not in STATES: raise CheckpointCorrupt("invalid checkpoint state")`
     **Direct Probe Observation**:
     Calling `kernel.checkpoint(..., state="WAITING_APPROVAL", ...)` raises:
     `CheckpointCorrupt: invalid checkpoint state`!
2. **EvidenceStore Staging Cleanup Race Condition**:
   - In `scp/epistemic/evidence_store.py:208-209`:
     `for leftover in staging.iterdir(): leftover.unlink(missing_ok=True)`
   - **Direct Probe Observation**:
     When Process B initializes `EvidenceStore` while Process A has written a staging file during `observe()`, Process B deletes Process A's staging file. Process A's subsequent `os.replace` crashes with:
     `FileNotFoundError: [WinError 2] The system cannot find the file specified: ...\.staging\... -> ...\blobs\...`
3. **`reality_test.py` Synthetic Callables Probe**:
   - Case 1 (0 callables): `{"ok": False, "status": "UNVERIFIED", "reason": "0 callables exercised successfully"}`
   - Case 2 (All callables raise): `{"ok": False, "status": "UNVERIFIED", "exceptions": [...]}`
   - Case 3 (1 callable passes, 1 raises): `{"ok": True, "status": "VERIFIED", "reason": "reality test passed, exercised 1 callables, 1 callable(s) raised"}` -> **Demonstrates partial pass masking latent failure**.
   - Case 4 (`sys.exit()` in callable): Intercepted by `_safe_call` without killing host runner process.
   - Case 5 (Default parameters execution): `_build_mock_args` injects `param.default` directly, executing functions with default arguments.

---

## 2. Logic Chain

### 2.1 Causal Chain 1: TaskKernel 18 Active Runtime States vs 15-State Mandate
- **Observation**: `AGENTS.md` and `tests/T09_golden_task/test_e2e_scp_complete.py` mandate a strict 15-state immutable state machine. However, `scp/task_kernel.py` defines 17 states in `STATES` and 18 states in `ALLOWED_TRANSITIONS`, introducing `WAITING_APPROVAL`.
- **Step 1 (Input/Trigger)**: Governance or policy engine evaluates an action requiring external approval and transitions the task from `PLANNING` to `WAITING_APPROVAL`.
- **Step 2 (Routing/Dispatch)**: Transition calls `TaskKernel.transition(task_id, "WAITING_APPROVAL")`.
- **Step 3 (Transition Execution)**: Transition succeeds because both `taskkernel.py:115` and `task_kernel.py:234` contain an explicit patched clause `and to_state != 'WAITING_APPROVAL'`. The event journal records `STATE_TRANSITION (PLANNING -> WAITING_APPROVAL)`.
- **Step 4 (Subsystem Side Effect - The Failure Vector)**: If a worker or recovery agent attempts to persist an intermediate checkpoint during this phase (`kernel.checkpoint(..., state="WAITING_APPROVAL", ...)`), `taskkernel.py:302` executes `if state not in STATES: raise CheckpointCorrupt('invalid checkpoint state')`.
- **Step 5 (Final Verdict)**: The transaction aborts with `CheckpointCorrupt`. Furthermore, upon system crash, `recover_on_boot()` does not recognize `WAITING_APPROVAL` in its recovery routing (`RUNNING->HUMAN_REVIEW`, `LEASED->RECOVERING`, `CHECKPOINTED->QUEUED`), placing `WAITING_APPROVAL` in `left_as_is` without monitoring or lease reconciliation.
- **Conclusion**: The introduction of `WAITING_APPROVAL` without adding it to `STATES` and `recover_on_boot` creates an uncheckpointable latent dead-end state.

### 2.2 Causal Chain 2: FA-02 Skip Paths and Baseline Technical Debt
- **Observation**: `t00_meta_audit.py` tracks 5 historical `BASELINE_DEBT` entries (4 skip instances, 1 manufactured VERIFIED string in `evidence_replay.py`).
- **Step 1 (Trigger)**: Execution of security tests (`test_no_hardcoded_token_in_source` and `test_bandit_no_new_high_severity_via_bandit`) on a standard runner environment.
- **Step 2 (Environment Gap)**:
  - `SCP_AUTH_TOKEN_SECRET` environment variable is not set.
  - `bandit` CLI binary is not installed on the system PATH (`bandit: The term 'bandit' is not recognized...`).
- **Step 3 (Execution Path)**: The tests detect the missing prerequisite and execute `pytest.skip(...)` rather than asserting fail-closed security invariants.
- **Step 4 (Impact)**: The security checks are completely bypassed in this environment, yet pytest exits 0.
- **Step 5 (DNA Evaluation)**: This satisfies DNA #22 (`PASS ≠ TRUE`). The tests pass purely because the execution branch was skipped, providing zero runtime evidence that source files are free from hardcoded secrets or high-severity vulnerabilities.

### 2.3 Causal Chain 3: Epistemic EvidenceStore Staging Cleanup Race Condition
- **Observation**: `EvidenceStore.__init__` unconditionally cleans the `.staging` folder with `leftover.unlink(missing_ok=True)`.
- **Step 1 (Trigger)**: Concurrent access or multi-process worker initialization (e.g., Worker 1 executes `observe()`, while Worker 2 or a supervisor initializes `EvidenceStore`).
- **Step 2 (Staging Write)**: Worker 1 writes content to `objects/.staging/<uuid>` and flushes/fsyncs the file handle.
- **Step 3 (Concurrent Deletion)**: Worker 2 initializes `EvidenceStore` pointing to the same `objects` directory; `__init__` iterates through `objects/.staging` and unlinks all files.
- **Step 4 (Atomic Rename Failure)**: Worker 1 attempts `os.replace(staging, blob_path)`. Since the staging file was unlinked by Worker 2, the OS raises `FileNotFoundError [WinError 2]`.
- **Step 5 (Impact)**: The observation fails, the database transaction is aborted, and evidence ingestion fails closed due to a filesystem race condition.

---

## 3. Caveats

1. **Host-Specific Temp File Contention**: On Windows, SQLite locks files during execution, and running `pytest` without `--basetemp` directs files to `%TEMP%\pytest-of-check`, which can fail with `[WinError 5] Access is denied` if concurrent processes hold handles. This is avoided when using `pytest.ini`'s `--basetemp=reports/pytest-basetemp`.
2. **External Dependencies**: Local environment lacks `bandit` on PATH and `SCP_AUTH_TOKEN_SECRET`, so security tests skip by design under current baseline debt rules.
3. **Multi-Platform Lineage**: These observations are gathered directly on the Windows 11 host. CI runners on Ubuntu/Linux may have different filesystem locking semantics (e.g., unlinking open files is permitted on POSIX, which would result in `os.replace` failing with `ENOENT` on POSIX as well).

---

## 4. Conclusion

- **Dynamic Execution Verdict**: **PASS_WITHIN_SCOPE** (with verified baseline debt).
  - All 515 tests in `tests/` pass synchronously.
  - Full suite (`pytest`) runs 547 passing tests with 1 skipped test (due to absent `SCP_AUTH_TOKEN_SECRET`).
  - `t00_meta_audit.py` confirms 0 new regressions against `origin/main`.
  - `verify_scp_test_skill_contract.py` confirms 14 gate bindings, 1 handoff binding, and 29 DNA principles intact.
- **Critical Subsystem Findings (DNA #26: Reality > Model)**:
  1. **TaskKernel State Machine Fracture**: `WAITING_APPROVAL` exists in `ALLOWED_TRANSITIONS` (making 18 states) but is missing from `STATES` (17 states) and the 15-state mandate. Calling `checkpoint(state='WAITING_APPROVAL')` fails with `CheckpointCorrupt`.
  2. **EvidenceStore Staging Race Condition**: Unsynchronized `staging.iterdir()` unlinks files actively being written by concurrent `observe()` callers, leading to `FileNotFoundError` during atomic rename.
  3. **`reality_test.py` Masking**: When synthetic callables have 1 passing and 1 failing function, `run_reality_test` declares `VERIFIED`, illustrating that a partial pass masks component-level failures.

---

## 5. Verification Method

To independently verify these findings, run the following exact commands in PowerShell from the project root (`c:\Users\check\Downloads\scp`):

1. **Verify Integrity Gate**:
   ```powershell
   python tools/t00_meta_audit.py
   python tools/verify_scp_test_skill_contract.py
   ```
2. **Verify Full Pytest Suite**:
   ```powershell
   pytest tests/
   pytest
   ```
3. **Verify Core Subsystem Suites**:
   ```powershell
   pytest tests/T04_kernel/ -v
   pytest tests/T06_verifier/ -v
   pytest tests/T09_golden_task/ -v
   pytest tests/T10_recovery/ -v
   ```
4. **Reproduce TaskKernel `WAITING_APPROVAL` Checkpoint Crash**:
   ```powershell
   python -c "from scp.task_kernel import TaskKernel; k = TaskKernel(':memory:'); k.create_task('t1', 'o', 'g'); k.checkpoint('t1', 'fake_lease', 's1', 'WAITING_APPROVAL', {}, 1, 'idem1')"
   ```
   *Expected result*: Raises `scp.task_kernel.CheckpointCorrupt: invalid checkpoint state`.
5. **Reproduce EvidenceStore Staging Race Condition**:
   ```powershell
   python -c "from pathlib import Path; import tempfile, uuid, os; from scp.epistemic.evidence_store import EvidenceStore; tmp = tempfile.mkdtemp(); s1 = EvidenceStore(Path(tmp)/'db.sqlite', Path(tmp)/'obj'); st = Path(tmp)/'obj'/'.staging'/uuid.uuid4().hex; st.write_bytes(b'x'); s2 = EvidenceStore(Path(tmp)/'db.sqlite', Path(tmp)/'obj'); os.replace(st, Path(tmp)/'obj'/'blobs'/'test')"
   ```
   *Expected result*: Raises `FileNotFoundError`.
