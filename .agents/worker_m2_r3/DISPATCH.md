## 2026-09-08T12:36:26Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Identity: You are Worker M2 (teamwork_preview_worker).
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_m2_r3
Original user request file: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_1\SCOPE.md
Explorer R3 analysis: c:\Users\check\Downloads\scp\.agents\explorer_r3\analysis.md
Explorer R3 handoff: c:\Users\check\Downloads\scp\.agents\explorer_r3\handoff.md

FILE WRITE OWNERSHIP: You exclusively own:
- c:\Users\check\Downloads\scp\scp\core\verifier_receipt.py (new module)
- c:\Users\check\Downloads\scp\scp\task_kernel_parts\taskkernel.py
- c:\Users\check\Downloads\scp\scp\hands\task_kernel_bridge.py
- c:\Users\check\Downloads\scp\scp\ask_kernel_adapter.py
- c:\Users\check\Downloads\scp\tests\T04_kernel\test_verifier_receipt_provenance.py (new test module)
Do NOT touch any other files outside this boundary.

Mission: Implement R3: Provenance Forgery Remediation (Verifier Receipts & Kernel Verification).
Key implementation tasks:
1. Create `scp/core/verifier_receipt.py`:
   - Define `VerifierReceipt` dataclass: `task_id: str, verifier_id: str, verdict: str, evidence_ref: str, issued_at: float, signature: str = ""`.
   - Define `InvalidReceiptSignatureError(KernelError, PermissionError)`.
   - Implement `canonical_receipt_bytes(receipt: VerifierReceipt) -> bytes`.
   - Implement `sign_verifier_receipt(receipt: VerifierReceipt, secret: str | None = None) -> VerifierReceipt` using HMAC-SHA256 with `SCP_VERIFIER_SECRET` (fallback `SCP_CAPABILITY_SECRET`).
   - Implement `verify_verifier_receipt(receipt: VerifierReceipt | dict, secret: str | None = None) -> bool` using constant-time `hmac.compare_digest`.
2. In `scp/task_kernel_parts/taskkernel.py`:
   - In `commit_verification_result(self, task_id, lease_id, verification_result)`: strictly require that `verification_result` is a valid `VerifierReceipt` or dict with valid HMAC signature. Call `verify_verifier_receipt()`; raise `InvalidReceiptSignatureError` if invalid or missing signature.
   - In `commit_completed()`: require valid signed receipt (or require callers to use `commit_verification_result`). Close GAP-P1 by strictly enforcing that task state MUST be `VERIFYING` (reject `RUNNING` -> `COMPLETED` bypass).
   - In journal event `TASK_COMPLETED`: record authentic `verifier_id` and receipt signature digest in event payload (closing GAP-P2).
3. In `scp/hands/task_kernel_bridge.py` and `scp/ask_kernel_adapter.py`:
   - Update receipt emission to produce genuine signed `VerifierReceipt` instances using `sign_verifier_receipt`.
4. In `tests/T04_kernel/test_verifier_receipt_provenance.py`:
   - Write comprehensive unit & regression tests:
     - Acceptance of authentic signed receipts -> commits COMPLETED.
     - Rejection of forged receipts (modified verdict, modified evidence_ref, altered verifier_id) -> raises error.
     - Rejection of unsigned receipts -> raises error.
     - Rejection of direct `RUNNING -> COMPLETED` transition without `VERIFYING`.
     - Verification of journal event records.
5. Run tests via `run_command`:
   - Run `python -m pytest tests/T04_kernel/test_verifier_receipt_provenance.py -v`
   - Run existing kernel tests: `python -m pytest tests/T04_kernel/ -q`
6. Prepare Coverage Matrix per FA-13 and verify all causal branches.

## 2026-09-08T12:39:42Z

**Context**: Server restart recovery for Worker M2 (R3 Remediation).
**Content**: The host server has restarted. Please resume your implementation immediately from where you stopped.
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables. DO NOT CHEAT.
Tasks:
1. Create `scp/core/verifier_receipt.py` with `VerifierReceipt`, HMAC-SHA256 signing, and verification.
2. Enforce receipt verification in `scp/task_kernel_parts/taskkernel.py` (`commit_verification_result`, `commit_completed`, close GAP-P1 state bypass, journal signature hash).
3. Update `scp/hands/task_kernel_bridge.py` and `scp/ask_kernel_adapter.py` to produce signed receipts.
4. Write tests in `tests/T04_kernel/test_verifier_receipt_provenance.py` and run them via run_command.
5. Create Coverage Matrix (FA-13) and write handoff to `.agents/worker_m2_r3/handoff.md`.
**Action**: Resume execution, run tests, and report back when complete.
