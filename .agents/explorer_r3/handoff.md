# Handoff Report: R3 Provenance Forgery (Verifier Receipts) Investigation

**Agent:** Explorer R3 (`teamwork_preview_explorer`)  
**Role:** Read-Only Investigation & Architecture Synthesis  
**Date:** 2026-09-08T12:34:30Z  
**Target:** R3 Remediation: Verifier Receipt Provenance Forgery  
**Detailed Technical Report:** `c:\Users\check\Downloads\scp\.agents\explorer_r3\analysis.md`

---

## 1. Observation

1. **`TaskKernel.commit_verification_result` in `scp/task_kernel_parts/taskkernel.py:1044-1050`:**
   ```python
   def commit_verification_result(self, task_id: str, lease_id: str, verification_result: dict[str, Any]) -> dict[str, Any]:
       if not isinstance(verification_result, dict) or verification_result.get('verdict') != 'VERIFIED':
           raise KernelError('completion requires verifier verdict VERIFIED')
       if not verification_result.get('verifier_id') or not verification_result.get('evidence_ref'):
           raise KernelError('completion requires verifier identity and evidence')
       return self.commit_completed(task_id, lease_id, 'VERIFIED', str(verification_result['evidence_ref']))
   ```
   *Observation:* There is **zero** cryptographic signature check. Any dictionary with `verdict: "VERIFIED"` and non-empty `verifier_id` and `evidence_ref` is accepted as valid verification.

2. **`TaskKernel.commit_completed` in `scp/task_kernel_parts/taskkernel.py:1051-1082`:**
   ```python
   def commit_completed(self, task_id: str, lease_id: str, verifier_verdict: str, evidence_ref: str) -> dict[str, Any]:
       if verifier_verdict != 'VERIFIED' or not evidence_ref:
           raise KernelError('completion requires independent VERIFIED verdict and evidence')
       self._begin()
       try:
           self._assert_lease(lease_id, task_id)
           task = self._task(task_id)
           if task['state'] not in {'VERIFYING', 'RUNNING'}:
               raise InvalidTransition(f"{task['state']}->COMPLETED")
           ...
           self._append_event(task_id, 'TASK_COMPLETED', old, 'COMPLETED', 'verifier', 'postcondition_verified', {'evidence_ref': evidence_ref, 'verifier_verdict': verifier_verdict, 'lease_id': lease_id})
   ```
   *Observation:*
   - `commit_completed()` can be invoked directly with raw strings without any receipt object.
   - Line 1058 allows `task['state'] == 'RUNNING'`, permitting workers to skip `VERIFYING` entirely.
   - Line 1073 hardcodes `actor: 'verifier'`, allowing a rogue worker to masquerade as an auditor in the SQLite journal.

3. **`TaskKernelHandsBridge.execute` in `scp/hands/task_kernel_bridge.py:465-489`:**
   ```python
   if bool(result.get("success")) and bool((result.get("verification") or {}).get("passed")):
       self.kernel.transition(task_id, "VERIFYING", actor="hands-kernel-bridge", reason="hands_result_observed")
       evidence_ref = self._evidence_ref(task_id, result)
       self.kernel.idempotency_complete(logical_key, evidence_ref)
       final_task = self.kernel.commit_verification_result(
           task_id,
           lease.lease_id,
           {
               "verdict": "VERIFIED",
               "verifier_id": "hands-kernel-result-verifier-v1",
               "evidence_ref": evidence_ref,
           },
       )
   ```
   *Observation:* The bridge synthesizes an unauthenticated dictionary in RAM without cryptographic provenance.

4. **`HandsExecutor.execute` in `scp/hands/hands_executor.py:105, 152, 155, 165, etc.`:**
   *Observation:* HandsExecutor emits unauthenticated dictionaries: `result["verification"] = {"passed": ..., "rule": definition.verifier}`.

5. **`AskKernelAdapter.finalize` in `scp/ask_kernel_adapter.py:391-393`:**
   ```python
   verification = await self.verify_response(req, response, task)
   if verification["verdict"] == "VERIFIED":
       final_task = self.kernel.commit_verification_result(task_id, lease_id, verification)
   ```
   *Observation:* `verify_response()` returns an unsigned dictionary (lines 311-322).

6. **Exploit Mandate Terminal Verification (FA-09):**
   Executed:
   ```bash
   python -c "
   import tempfile
   from pathlib import Path
   from scp.task_kernel import TaskKernel
   with tempfile.TemporaryDirectory() as tmp_dir:
       kernel = TaskKernel(Path(tmp_dir) / 'kernel.sqlite3')
       kernel.create_task('t1', 'o1', 'g1')
       for s in ('PLANNING', 'READY', 'QUEUED'): kernel.transition('t1', s)
       lease = kernel.claim('t1', 'w1')
       kernel.start('t1', lease.lease_id)
       kernel.transition('t1', 'VERIFYING')
       res = kernel.commit_verification_result('t1', lease.lease_id, {'verdict': 'VERIFIED', 'verifier_id': 'malicious-worker', 'evidence_ref': 'fake://ref'})
       print('Task State:', res['state'])
       kernel.close()
   "
   ```
   *Output:*
   ```text
   Task State: COMPLETED
   ```
   Proving conclusively that forged receipts commit successfully.

7. **Baseline Test Status:**
   - `pytest tests/T04_kernel`: 140 passed in 10.81s.
   - `pytest tests/T06_verifier`: 26 passed in 14.79s.

---

## 2. Logic Chain

1. **Step 1 (Observation 1 & 6):** `commit_verification_result()` accepts any raw dictionary with `verdict == 'VERIFIED'`, checking neither cryptographic signatures nor issuer identity.
2. **Step 2 (Observation 2):** `commit_completed()` permits raw string parameters and accepts tasks in `RUNNING` state, skipping the `VERIFYING` state.
3. **Step 3 (Observation 1, 2, 6):** Therefore, any worker holding an active lease can manufacture a fake verification outcome, bypass the postcondition verifier, and terminate tasks in `COMPLETED`.
4. **Step 4 (Observation 3, 4, 5):** The upstream callers (`HandsExecutor`, `TaskKernelHandsBridge`, `AskKernelAdapter`) currently emit and consume unsigned Python dictionaries in RAM.
5. **Step 5 (Synthesis):** To fix R3 fail-closed under Zero-Trust principles, we must introduce:
   - A dedicated module `scp/core/verifier_receipt.py` with HMAC-SHA256 signing and verification using `SCP_VERIFIER_SECRET` (fallback `SCP_CAPABILITY_SECRET`).
   - Domain-separated canonical serialization: `canonical_receipt_bytes()`.
   - Kernel enforcement in `commit_verification_result()` and `commit_completed()` rejecting any unproven or forged receipt.
   - Elimination of the `RUNNING -> COMPLETED` backdoor (GAP-P1).
   - Event journal recording authentic `verifier_id` and `signature_digest` (GAP-P2).

---

## 3. Caveats

- **Scope Boundary:** This investigation was strictly read-only per the explorer role constraints. No production code was modified.
- **Existing Test Suite Adaptation:** Currently, multiple unit tests in `tests/T04_kernel/` call `commit_completed()` with test strings without signatures. When the implementer enforces HMAC receipts fail-closed in `TaskKernel`, those tests must be updated to pass signed test receipts (or use a test signing helper).

---

## 4. Conclusion

- **Vulnerability Status:** R3 (Provenance Forgery) is **CONFIRMED and PROVEN** by empirical exploit execution.
- **Remediation Feasibility:** HIGH. The architecture mirrors the successful implementation of GAP-13 (`verify_approval_authority`) and GAP-08 (`CapabilityToken`).
- **Peripheral Findings:** 4 peripheral gaps identified (GAP-P1 to GAP-P4), with GAP-P1 (`RUNNING -> COMPLETED` state skip) being high severity and directly remediable alongside R3.
- **Next Step:** Implementer agent can immediately execute the patch blueprint detailed in `c:\Users\check\Downloads\scp\.agents\explorer_r3\analysis.md`.

---

## 5. Verification Method

To independently verify the findings in this report:

1. **Reproduce the Vulnerability:**
   Run the terminal probe:
   ```bash
   python -c "import tempfile; from pathlib import Path; from scp.task_kernel import TaskKernel; d = tempfile.mkdtemp(); k = TaskKernel(Path(d)/'k.sqlite3'); k.create_task('t', 'o', 'g'); [k.transition('t', s) for s in ('PLANNING', 'READY', 'QUEUED')]; l = k.claim('t', 'w'); k.start('t', l.lease_id); k.transition('t', 'VERIFYING'); r = k.commit_verification_result('t', l.lease_id, {'verdict': 'VERIFIED', 'verifier_id': 'rogue', 'evidence_ref': 'fake'}); print('VERDICT:', r['state']); k.close()"
   ```
   *Expected output:* `VERDICT: COMPLETED` (proves absence of signature validation).

2. **Verify Baseline Kernel Tests:**
   ```bash
   python -m pytest tests/T04_kernel
   ```
   *Expected output:* 140 passed.

3. **Verify Baseline Verifier Tests:**
   ```bash
   python -m pytest tests/T06_verifier
   ```
   *Expected output:* 26 passed.

4. **Review Technical Specification:**
   Inspect `c:\Users\check\Downloads\scp\.agents\explorer_r3\analysis.md` for the line-by-line call graph, HMAC scheme, and FA-13 causal coverage matrix.
