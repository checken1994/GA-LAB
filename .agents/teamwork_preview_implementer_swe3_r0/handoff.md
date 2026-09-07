# Handoff Report: GAP-11 Remediation & Empirical Causal Closure

**Implementer:** teamwork_preview_implementer_swe3_r0  
**Parent Orchestrator:** teamwork_preview_swe_3  
**Date:** 2026-09-08T00:40:00+07:00  
**Target File:** `scp/task_kernel_parts/taskkernel.py`  
**Test Suite:** `tests/T04_kernel/` (67/67 PASS)  
**Meta-Audit:** `tools/t00_meta_audit.py` (0 new regressions)  
**Probe Status:** `tools/probes/probe_gap11.py` (GREEN, raw SQLite verified)  

---

## 1. Executive Summary & Diff Summary

### R1. GAP-11 Elimination
In `scp/task_kernel_parts/taskkernel.py`, within `TaskKernel.transition()`, an explicit guard was inserted before starting any database transaction or OCC lock:
```python
if to_state == "COMPLETED":
    raise InvalidTransition(
        "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
    )
```
This guarantees that:
- Any direct attempt to transition to `COMPLETED` raises `InvalidTransition` immediately.
- Transition to `COMPLETED` is exclusively available via `commit_completed()` (or `commit_verification_result()`), which strictly demands independent verifier identity (`verifier_id`), valid postcondition evidence (`evidence_ref`), and active lease authority.

### Full Diff of Core Changes

```diff
--- a/scp/task_kernel_parts/taskkernel.py
+++ b/scp/task_kernel_parts/taskkernel.py
@@ -250,6 +250,10 @@ class TaskKernel:
     ) -> dict[str, Any]:
         if to_state not in STATES and to_state != "WAITING_APPROVAL":
             raise InvalidTransition(f"unknown target state {to_state}")
+        if to_state == "COMPLETED":
+            raise InvalidTransition(
+                "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
+            )
         self._begin()
         try:
             if event_id:

--- a/tests/T04_kernel/test_adversarial_kernel_flaws.py
+++ b/tests/T04_kernel/test_adversarial_kernel_flaws.py
@@ -390,3 +390,43 @@ def test_kernel_cancel_method_alias_and_quota_cleanup(tmp_path):
         kernel.close()
 
 
+def test_gap11_raw_transition_to_completed_is_strictly_forbidden(tmp_path):
+    """GAP-11: Raw transition() to COMPLETED must raise InvalidTransition.
+
+    Tasks can only be completed via commit_completed() with valid evidence and lease.
+    """
+    kernel = TaskKernel(tmp_path / "kernel.sqlite3")
+    try:
+        lease = _setup_running_task(kernel, "adv-gap11-1", "owner-gap11")
+        kernel.transition("adv-gap11-1", "VERIFYING")
+
+        # Rogue attempt: bypass evidence verification via transition()
+        with pytest.raises(InvalidTransition) as excinfo:
+            kernel.transition(
+                "adv-gap11-1",
+                "COMPLETED",
+                lease_id=lease.lease_id,
+                actor="rogue_worker",
+                reason="fake pass attempt",
+            )
+        assert "direct transition to COMPLETED is forbidden" in str(excinfo.value)
+
+        # Verify DB state is unmodified
+        task = kernel.get_task("adv-gap11-1")
+        assert task["state"] == "VERIFYING"
+        events = kernel.get_events("adv-gap11-1")
+        assert not any(e["to_state"] == "COMPLETED" for e in events)
+
+        # Legitimate path: commit_completed with valid evidence
+        completed = kernel.commit_completed(
+            "adv-gap11-1",
+            lease.lease_id,
+            "VERIFIED",
+            "evidence://audit/proof-hash-1234",
+        )
+        assert completed["state"] == "COMPLETED"
+    finally:
+        kernel.close()
```

---

## 2. Empirical Verification Logs & Raw SQLite Inspection (FA-12)

### 2.1 Terminal Execution of `tools/probes/probe_gap11.py`
```text
GREEN: Blocked with InvalidTransition: direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence
RAW_SQLITE_TASKS_ROW: {'task_id': 'task_probe_11', 'state': 'VERIFYING', 'version': 7, 'active_lease_id': 'lease_85bad1930a847df893d7d86b'}
RAW_SQLITE_EVENTS_COUNT: 7
RAW_SQLITE_EVENT: seq=1 type=TASK_CREATED from=None to=CREATED actor=kernel
RAW_SQLITE_EVENT: seq=2 type=STATE_TRANSITION from=CREATED to=PLANNING actor=kernel
RAW_SQLITE_EVENT: seq=3 type=STATE_TRANSITION from=PLANNING to=READY actor=kernel
RAW_SQLITE_EVENT: seq=4 type=STATE_TRANSITION from=READY to=QUEUED actor=kernel
RAW_SQLITE_EVENT: seq=5 type=LEASE_GRANTED from=QUEUED to=LEASED actor=kernel
RAW_SQLITE_EVENT: seq=6 type=STATE_TRANSITION from=LEASED to=RUNNING actor=kernel
RAW_SQLITE_EVENT: seq=7 type=STATE_TRANSITION from=RUNNING to=VERIFYING actor=kernel
```

### 2.2 Empirical Analysis of SQLite DB State
- **Task row in `tasks` table:** State stayed `VERIFYING`; OCC version remained at 7; lease remained bound.
- **Event ledger in `events` table:** Exactly 7 events recorded. No event for `COMPLETED` was written.
- **Fail-Closed Boundary:** The failure was triggered before `_begin()`, ensuring zero database corruption and zero lock contention.

---

## 3. Peripheral Audit & Mermaid Causal Graph (FA-11)

Full audit and whole-file Mermaid Causal Graph documented in `EMERGENCY_GAP_REPORT.md`.

### Summary of Peripheral Findings:
1. **GAP-12 (Unverified FAILED Transition):** Any worker holding a lease can call `transition(task_id, "FAILED")` without submitting verifier indictment or failure classification, permanently locking the task into terminal `FAILED`.
   - Probe: `tools/probes/probe_gap11_failed.py` confirmed RED.
2. **GAP-13 (Unauthenticated WAITING_APPROVAL Bypass):** Calling `transition(task_id, "READY")` on tasks in `WAITING_APPROVAL` succeeds without requiring approval token, signature, or authority verification.
3. **Anti-Scope Creep Compliance:** Zero unauthorized code changes were made for GAP-12 or GAP-13.

---

## 4. Regression Test Suite & Meta-Audit Results

### 4.1 Pytest Suite: `pytest tests/T04_kernel/ -q`
```text
...................................................................      [100%]
67 passed in 6.02s
```
*(All 66 baseline tests PASS + 1 new test `test_gap11_raw_transition_to_completed_is_strictly_forbidden` PASS).*

### 4.2 Meta-Audit: `python tools/t00_meta_audit.py`
```text
[T00 Meta-Audit] Starting Test-Integrity Regression Authority...
[T00 Meta-Audit] Trusted Base: origin/main
[T00 Meta-Audit] Collecting baseline pytest nodeids (origin/main)...
[T00 Meta-Audit] Collecting candidate pytest nodeids...
[T00 Meta-Audit] All integrity checks passed (0 new regressions).
```

---

## 5. Traceability
- Checked `spec/scp_target_test_coverage.yaml`: verified that `taskkernel.py` file SHA is not tracked in that manifest.
