# Adversarial Challenge Report: GAP-12 Probe & Downstream Impact

- **Agent:** `challenger_delta_2` (`teamwork_preview_challenger`)
- **Roles:** critic, specialist
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\challenger_delta_2`
- **Recipient / Parent Conversation ID:** `55c745a6-7ce1-4c1e-9385-e614d0c57946`
- **Date:** 2026-09-08T01:36:30+07:00
- **Evaluation Subject:** Milestone M4 (`worker_m4_probe/handoff.md` and `tools/probes/probe_gap12_delta_audit.py`)
- **Verdict:** `REQUEST_CHANGES`

---

## 1. Observation

### 1.1 Direct Reproduction of Baseline Claims
1. **Probe Execution:**
   Command executed in terminal:
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   Exit code: `0`.
   Verbatim output:
   ```text
   ================================================================================
   SCP-OMEGA DELTA AUDIT: GAP-12 EMPIRICAL PROBE
   Subsystem: TaskKernel State Machine
   Invariants Tested:
     - INV-GAP12-01: Prohibition of Raw Unverified Transition to Terminal FAILED
     - INV-GAP12-02: Mandatory Indictment & Evidence for Failure Commitment
     - INV-GAP12-03: Preservation of Retry Budget and Recovery Routing
     - INV-GAP12-04: System Authority Separation for Pre-execution Indictment
   ================================================================================
   ...
   Anti-Placebo Contract Status:
     >> RED STATE CONFIRMED: All 4 exploit vectors succeed on current codebase.
     >> Vulnerability GAP-12 is actively exploitable at the database layer.
     >> Anti-Placebo Falsification Condition: Upon implementing INV-GAP12-01 through 04,
        calls to transition(..., 'FAILED') must raise InvalidTransition, causing this probe
        to record PROTECTED_GREEN for all vectors.
   ================================================================================
   ```
   Direct SQLite inspection confirmed 4 tasks mutated to `state='FAILED'` and 4 `STATE_TRANSITION` events appended.

2. **Kernel Test Suite:**
   Command executed in terminal:
   ```powershell
   pytest tests/T04_kernel -q
   ```
   Result: `78 passed in 7.01s`, exit code `0`.
   No regressions exist on the current baseline commit.

### 1.2 Downstream Caller Code Inspection
1. **`scp/ask_kernel_adapter.py` (lines 426–447):**
   ```python
   def fail(self, task: dict[str, Any], reason: str) -> None:
       try:
           current = self.kernel.get_task(task["task_id"])
           if current["state"] not in _TERMINAL:
               self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)
           with _TRACE_LOCK:
               self.trace.append(...)
       except Exception as exc:  # non-fatal audit fallback; original error wins
           try:
               from scp.core.exception_policy import observe_nonfatal
               observe_nonfatal(component="scp/ask_kernel_adapter.py:fail", exception_type=type(exc).__name__)
           except Exception:
               return
   ```
   `AskKernelAdapter.fail()` invokes raw `self.kernel.transition(task["task_id"], "FAILED", ...)` without passing `lease_id` and without attaching structured failure evidence. Crucially, it wraps the transition in `try: ... except Exception:`, suppressing any exception via non-fatal observation.

2. **`tests/T04_kernel/test_adversarial_kernel_flaws.py` (lines 886–891):**
   ```python
   # Part 1: adapter.fail() sets task state to FAILED
   task1 = adapter.begin(req.question, list(req.contexts), req.retrieved_context, "session-fail")
   t1_id = task1["task_id"]
   assert adapter.kernel.get_task(t1_id)["state"] == "RUNNING"
   adapter.fail(task1, reason="upstream handler failed")
   assert adapter.kernel.get_task(t1_id)["state"] == "FAILED"
   ```
   The existing test suite explicitly asserts that `adapter.fail()` causes the task state to become `"FAILED"`.

3. **`scp/hands/task_kernel_bridge.py` (lines 445–457 and 582–594):**
   Both `_policy_blocked_before_dispatch` and bridge pre-dispatch error handling directly call `self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", ...)`.
   In `tests/T03_capability/test_hands_authority_pep.py` (lines 207–208, 218, 252–253, 283–284), tests assert:
   ```python
   assert kernel_info.get("taskState") == "FAILED"
   assert db_task["state"] == "FAILED"
   ```

### 1.3 Probe Implementation Deficiencies (`tools/probes/probe_gap12_delta_audit.py`)
1. **Flaw 1: Missing GREEN Evaluation Branch (lines 295–305):**
   ```python
   if all_red and results.get("sqlite_tasks_state_failed") and results.get("sqlite_events_count_failed") == 4:
       print("  >> RED STATE CONFIRMED: All 4 exploit vectors succeed on current codebase.")
       ...
       results["overall_verdict"] = "RED_VULNERABILITY_PROVEN"
   else:
       print("  >> Probe did not reproduce all vulnerabilities as expected.")
       results["overall_verdict"] = "UNEXPECTED_STATE"
   ```
   When all 4 vectors are successfully blocked (the GREEN state), `all_red` is `False`. The probe falls into `else:`, prints `" >> Probe did not reproduce all vulnerabilities as expected."`, and sets `overall_verdict = "UNEXPECTED_STATE"`. It possesses NO explicit `ALL_VECTORS_PROTECTED_GREEN` branch.

2. **Flaw 2: Placebo Exception Masking (lines 104, 142, 181, 220):**
   ```python
   except Exception as exc:
       print(f"[*] [GREEN] Call blocked with exception: {type(exc).__name__}: {exc}")
       results["vector_1"]["status"] = f"PROTECTED_GREEN_{type(exc).__name__}"
   ```
   Catching blanket `Exception` misclassifies arbitrary unexpected crashes (e.g. `AttributeError`, `KeyError`, `OperationalError: disk full`) as `PROTECTED_GREEN`.

### 1.4 Empirical Stress Harness Execution Output
To comply with FA-08 and FA-09, an empirical stress harness was created at `tools/probes/stress_test_gap12_downstream_and_probe.py` and executed:
```powershell
python tools/probes/stress_test_gap12_downstream_and_probe.py
```
Exit code: `0`.
Verbatim stdout extract:
```text
[MUTATION 1 RESULT]
Overall verdict when properly blocked: UNEXPECTED_STATE
  vector_1: PROTECTED_GREEN_InvalidTransition
  vector_2: PROTECTED_GREEN_InvalidTransition
  vector_3: PROTECTED_GREEN_InvalidTransition
  vector_4: PROTECTED_GREEN_InvalidTransition

[MUTATION 2 RESULT]
Status for vector 1 when an unrelated AttributeError is raised:
  vector_1 status: PROTECTED_GREEN_AttributeError

[DOWNSTREAM IMPACT TEST: AskKernelAdapter.fail()]
Task before fail(): ID=ask-7685536846f5d8ab650e2700, State=RUNNING
Task after fail() under patched TaskKernel: State=RUNNING
Is task silently stuck in RUNNING because fail() swallowed InvalidTransition? True

================================================================================
SUMMARY OF EMPIRICAL FINDINGS:
  1. Probe post-fix overall_verdict: UNEXPECTED_STATE (Should be GREEN_PROTECTED, but is UNEXPECTED_STATE)
  2. Probe placebo crash vulnerability: PROTECTED_GREEN_AttributeError (Unrelated AttributeError labeled as PROTECTED_GREEN)
  3. AskKernelAdapter downstream impact: Task stuck in RUNNING=True
================================================================================
```

---

## 2. Logic Chain

1. **Validity of Red State Proof (Observation 1.1):**
   The probe successfully proves that `transition(..., "FAILED")` is unguarded on the current commit, violating invariants INV-GAP12-01 through INV-GAP12-04 at the raw database level. The worker's claim of a RED baseline is empirically verified.

2. **Probe Logic Chain & Flaw Identification (Observations 1.3 & 1.4):**
   - *Step 2A (Missing Green Branch):* The probe is designed as an Anti-Placebo gate that must verify both RED before fix and GREEN after fix. However, when simulated with `InvalidTransition` (Mutation 1), the probe terminates with `UNEXPECTED_STATE`. A testing harness whose post-fix state is indistinguishable from an anomalous run is logically defective.
   - *Step 2B (Placebo Masking):* DNA principle #22 and the Anti-Placebo protocol mandate that an internal defect must not be interpreted as security enforcement. In Mutation 2, injecting an unrelated `AttributeError` produced `PROTECTED_GREEN_AttributeError`. The probe must strictly demand `InvalidTransition` (or `StaleLease`).

3. **Downstream Caller Blast Radius (Observations 1.2 & 1.4):**
   - *Step 3A:* When GAP-12 is remediated in `TaskKernel.transition()` by forbidding direct transitions to `FAILED`, any call to `transition(..., "FAILED")` will raise `InvalidTransition`.
   - *Step 3B:* In `AskKernelAdapter.fail()`, the exception is swallowed by the audit error handler. The task remains physically in `RUNNING`.
   - *Step 3C:* As proven in Observation 1.4, `task_after["state"] == "RUNNING"`, causing tasks to hang indefinitely in active execution and blocking queues.
   - *Step 3D:* Furthermore, `test_ask_kernel_adapter_lifecycle` in `tests/T04_kernel/test_adversarial_kernel_flaws.py` and bridge tests in `tests/T03_capability/test_hands_authority_pep.py` will experience immediate test failures because they assert `task["state"] == "FAILED"`.
   - *Step 3E:* Therefore, fixing GAP-12 cannot be treated as an isolated patch inside `taskkernel.py`. The remediation architecture (M5) MUST introduce `commit_failed()` and wire it into both `AskKernelAdapter` and `TaskKernelBridge`.

---

## 3. Caveats

1. **Production Code Untouched:** In accordance with the critical constraint, no files in `scp/` were modified.
2. **Stress Test File Presence:** `tools/probes/stress_test_gap12_downstream_and_probe.py` was created to empirically substantiate FA-09. It does not alter runtime behavior and can be run at any time to re-verify findings.
3. **GAP-13 Boundary:** Pre-execution admission control (`WAITING_APPROVAL -> READY`) remains out-of-scope for GAP-12.

---

## 4. Conclusion

- **Verdict:** `REQUEST_CHANGES`.
- **Rationale:**
  While the RED state of GAP-12 is genuinely proven, the current probe script in `tools/probes/probe_gap12_delta_audit.py` fails the Anti-Placebo and Falsification rigor requirements:
  1. It classifies unrelated crashes (`AttributeError`) as `PROTECTED_GREEN`.
  2. It returns `UNEXPECTED_STATE` instead of `ALL_VECTORS_PROTECTED_GREEN` when the fix is applied.
  3. The downstream integration blast radius has not been accounted for: remediating `TaskKernel` without migrating `AskKernelAdapter.fail()` and `TaskKernelBridge` will silently trap tasks in `RUNNING` and break kernel and capability regression tests.

### Required Actions for Worker / Orchestrator:
1. **Harden `tools/probes/probe_gap12_delta_audit.py`:**
   - Replace blanket `except Exception as exc:` with `except InvalidTransition as exc:` (or classify unexpected exceptions as `CRASH_ERROR`).
   - Add explicit logic in the summary block:
     ```python
     if all_green and results.get("sqlite_events_count_failed") == 0:
         results["overall_verdict"] = "ALL_VECTORS_PROTECTED_GREEN"
     ```
2. **Scope M5 Evolution Architecture:**
   - In M5, specify `TaskKernel.commit_failed(task_id, lease_id, indictment: dict[str, Any])` requiring valid lease authority and failure evidence.
   - Migrate `AskKernelAdapter.fail()` and `TaskKernelBridge` to use `commit_failed()`.

---

## 5. Verification Method

To independently verify all findings and stress tests:

1. **Verify Baseline Probe (Current RED State):**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   Expect: Exit code `0`, 4 vectors `VULNERABILITY_PROVEN_RED`.

2. **Verify Regression Suite:**
   ```powershell
   pytest tests/T04_kernel -q
   ```
   Expect: `78 passed in ~7s`.

3. **Run Adversarial Stress Harness (Proving Probe & Caller Flaws):**
   ```powershell
   python tools/probes/stress_test_gap12_downstream_and_probe.py
   ```
   Expect: Exit code `0`, proving:
   - Post-fix probe returns `UNEXPECTED_STATE` instead of green.
   - Placebo `AttributeError` is masked as `PROTECTED_GREEN_AttributeError`.
   - `AskKernelAdapter.fail()` leaves tasks stuck in `RUNNING`.

4. **Invalidation Conditions:**
   - This critique would be invalidated if `probe_gap12_delta_audit.py` already had a dedicated `ALL_VECTORS_PROTECTED_GREEN` verdict branch and rejected non-`InvalidTransition` exceptions.
   - This critique would be invalidated if `AskKernelAdapter.fail()` did not call `transition(..., "FAILED")`.
