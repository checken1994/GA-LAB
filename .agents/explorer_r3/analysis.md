# R3 Investigation & Architectural Analysis: Provenance Forgery (Verifier Receipts)

**Auditor:** Explorer R3 (teamwork_preview_explorer)  
**Date:** 2026-09-08T12:34:00Z  
**Standards:** Zero-Trust, Fail-Closed, FA-01 to FA-13, Exploit Mandate (FA-09), Peripheral Audit (FA-11), SCP DNA (29 Principles).  
**Target Codebase:**
- `scp/task_kernel_parts/taskkernel.py` & `scp/task_kernel.py`
- `scp/hands/task_kernel_bridge.py`
- `scp/hands/hands_executor.py`
- `scp/hands/planner.py`
- `scp/ask_kernel_adapter.py`
- `scp/verifier.py`

---

## 1. Executive Summary & Problem Statement

In the SCP Agent OS architecture, the Task Kernel acts as the authoritative source of truth for task lifecycle, durable state transitions, and event journaling. When a task completes execution, it must transition from `VERIFYING` to `COMPLETED` based exclusively on **independent, verifiable evidence** (DNA #5, #14, and `scp-reality-verifier` / `scp-task-kernel-review` skills).

### The Vulnerability (R3: Provenance Forgery)
Currently, `TaskKernel.commit_verification_result()` and `TaskKernel.commit_completed()` accept completely unauthenticated, raw Python dictionaries or strings as verification results.
1. Any leased worker (or compromised worker process) can fabricate a synthetic dictionary:
   ```python
   forged_receipt = {
       "verdict": "VERIFIED",
       "verifier_id": "trusted-postcondition-verifier",
       "evidence_ref": "fake://attacker-fabricated-evidence",
   }
   kernel.commit_verification_result(task_id, lease_id, forged_receipt)
   ```
   Or call `kernel.commit_completed(task_id, lease_id, "VERIFIED", "fake://evidence")` directly!
2. `TaskKernel` does **not** perform any cryptographic signature verification, HMAC validation, or origin authentication on this receipt.
3. `TaskKernel` writes an event into the append-only event journal with `actor: "verifier"` and `reason: "postcondition_verified"`, falsely attesting that an independent verifier validated the task when in fact no verifier was ever invoked.
4. Furthermore, `commit_completed()` permits a task in `RUNNING` to jump directly to `COMPLETED`, completely bypassing the `VERIFYING` state.

---

## 2. Root Cause Analysis (Why-Chain & DNA Principles)

Following DNA #1, #18, and #19:

1. **Why can workers forge verification receipts?**
   Because `TaskKernel.commit_verification_result()` and `commit_completed()` treat the worker as an authoritative courier of verification data, checking only that the caller holds an active lease, but never checking if the receipt itself was issued by an independent verifier.
2. **Why does holding an active lease not guarantee valid verification?**
   Because a lease only grants execution authority to a worker; it does **not** grant verifier authority. The worker is the executor, not the auditor (DNA #5: Shared Origin Blind Spot; DNA #14: Majority / Self-Attestation is not Proof).
3. **Why did `HandsExecutor` and `TaskKernelHandsBridge` emit raw `verification.passed`?**
   `HandsExecutor` sets `result["verification"] = {"passed": ...}` as a local Python dictionary in RAM. `TaskKernelHandsBridge` inspects `result["verification"]["passed"]`, synthesizes `"verifier_id": "hands-kernel-result-verifier-v1"`, and passes it to `TaskKernel`. Neither component generates or verifies a cryptographic signature.
4. **Why is this a critical Agent OS failure?**
   An Agent OS cannot operate autonomously 24/7 if workers can falsely report success for failed, hallucinated, or malicious operations. A task must never reach terminal `COMPLETED` without unforgeable cryptographic proof of independent verification.

---

## 3. Line-by-Line Call Graph (Navigation Map)

The following call graph traces how verification receipts currently flow from tool execution into TaskKernel, highlighting the exact vulnerability injection points:

```
[External Request: /ask or /v3/hands/execute]
   │
   ├── Path A: AskKernelAdapter (/ask)
   │     │
   │     ├── 1. `AskKernelAdapter.submit()` (ask_kernel_adapter.py:165)
   │     │      └─► `TaskKernel.create_task()` (taskkernel.py:346) -> State: CREATED
   │     │      └─► `TaskKernel.claim()` (taskkernel.py:510) -> State: LEASED
   │     │      └─► `TaskKernel.start()` (taskkernel.py:613) -> State: RUNNING
   │     │
   │     ├── 2. LLM Execution & RAG Context Retrieval
   │     │
   │     ├── 3. `AskKernelAdapter.finalize()` (ask_kernel_adapter.py:345)
   │     │      ├─► `TaskKernel.transition(task_id, "VERIFYING")` (taskkernel.py:365) [Line 384]
   │     │      │
   │     │      ├─► `AskKernelAdapter.verify_response()` (ask_kernel_adapter.py:270) [Line 391]
   │     │      │     └─► Evaluates checks dict (grounded_ratio, checks)
   │     │      │     └─► [UNAUTHENTICATED RETURN]: Returns dict with "verdict": "VERIFIED", "verifier_id": "scp-ask-rag-verifier-v2"
   │     │      │          (NO CRYPTOGRAPHIC SIGNATURE GENERATED)
   │     │      │
   │     │      └─► [VULNERABILITY CALL]: `TaskKernel.commit_verification_result(task_id, lease_id, verification)` [Line 393]
   │     │
   │     └── 4. `TaskKernel.commit_verification_result()` (taskkernel.py:1044)
   │            ├─► [NO SIGNATURE CHECK]: Only checks `isinstance(dict)` and `verdict == 'VERIFIED'` [Line 1045]
   │            └─► Calls `self.commit_completed(task_id, lease_id, 'VERIFIED', str(verification_result['evidence_ref']))` [Line 1049]
   │
   ├── Path B: Hands Side-Effect Bridge (/v3/hands/execute)
   │     │
   │     ├── 1. `TaskKernelHandsBridge.execute()` (task_kernel_bridge.py:317)
   │     │      └─► Creates task, claims lease, records checkpoint.
   │     │
   │     ├── 2. `HandsExecutor.execute()` (hands_executor.py:107)
   │     │      └─► Action executed (e.g. pc.read_file, pc.write_file, pc.status, etc.)
   │     │      └─► [EMISSION OF verification.passed]: In-memory dictionary generated:
   │     │          `result["verification"] = {"passed": bool(...), "rule": definition.verifier}`
   │     │          (hands_executor.py:105, 142, 152, 155, 165, 170, 173, etc.)
   │     │
   │     ├── 3. `TaskKernelHandsBridge` result evaluation (task_kernel_bridge.py:465)
   │     │      ├─► Checks: `if bool(result.get("success")) and bool((result.get("verification") or {}).get("passed")):` [Line 465]
   │     │      ├─► `TaskKernel.transition(task_id, "VERIFYING")` [Line 467]
   │     │      ├─► `TaskKernel.idempotency_complete(logical_key, evidence_ref)` [Line 471]
   │     │      └─► [SYNTHESIS OF UNVERIFIED RECEIPT]:
   │     │          `TaskKernel.commit_verification_result(task_id, lease.lease_id, {"verdict": "VERIFIED", "verifier_id": "hands-kernel-result-verifier-v1", "evidence_ref": evidence_ref})` [Line 473]
   │     │
   │     └── 4. `TaskKernel.commit_verification_result()` -> `TaskKernel.commit_completed()`
   │
   └── Path C: Direct Adversarial Forgery (The Exploit Path)
         │
         ├── Worker possesses active lease for `task_id`.
         ├── Exploit C1: Worker manufactures synthetic receipt:
         │   `kernel.commit_verification_result(task_id, lease_id, {"verdict": "VERIFIED", "verifier_id": "rogue", "evidence_ref": "fake"})`
         ├── Exploit C2: Worker calls `commit_completed` directly:
         │   `kernel.commit_completed(task_id, lease_id, "VERIFIED", "fake://url")`
         ├── Exploit C3: Worker calls `commit_completed` while still in `RUNNING` (bypassing `VERIFYING`):
         │   `taskkernel.py:1058` checks `if task['state'] not in {'VERIFYING', 'RUNNING'}:` -> RUNNING is accepted!
         │
         └── Result: `TaskKernel` commits `state='COMPLETED'` to SQLite, releases lease,
             and writes `events` table row with `actor='verifier'`, `reason='postcondition_verified'`.
             Tampering is completely undetected.
```

---

## 4. Empirical Vulnerability Proof (FA-09 Compliance)

In strict compliance with **FA-09 (The Exploit Mandate)**, an independent exploit simulation script was executed against `TaskKernel` to empirically prove that unverified and forged receipts are accepted by the current implementation.

### Physical Terminal Execution:
```bash
python -c "
import tempfile
from pathlib import Path
from scp.task_kernel import TaskKernel

with tempfile.TemporaryDirectory() as tmp_dir:
    db_path = Path(tmp_dir) / 'kernel.sqlite3'
    kernel = TaskKernel(db_path)
    try:
        kernel.create_task('task-forgery-1', 'owner-1', 'test forgery')
        kernel.transition('task-forgery-1', 'PLANNING')
        kernel.transition('task-forgery-1', 'READY')
        kernel.transition('task-forgery-1', 'QUEUED')
        lease = kernel.claim('task-forgery-1', 'worker-1', ttl_seconds=30)
        kernel.start('task-forgery-1', lease.lease_id)
        kernel.transition('task-forgery-1', 'VERIFYING')

        # Worker fabricates an arbitrary unauthenticated receipt
        forged_receipt = {
            'verdict': 'VERIFIED',
            'verifier_id': 'malicious-worker-fake-verifier',
            'evidence_ref': 'fake://attacker-controlled-evidence',
        }

        # Kernel commits it without verifying any signature!
        res = kernel.commit_verification_result('task-forgery-1', lease.lease_id, forged_receipt)
        print('VULNERABILITY PROVEN:')
        print('Task State:', res['state'])
        journal = kernel.verify_journal('task-forgery-1')
        print('Journal valid:', journal['hash_chain_valid'])
        print('Journal event count:', journal['event_count'])

        # Variant 2: Direct commit_completed bypassing VERIFYING state
        kernel.create_task('task-forgery-2', 'owner-1', 'test direct commit')
        kernel.transition('task-forgery-2', 'PLANNING')
        kernel.transition('task-forgery-2', 'READY')
        kernel.transition('task-forgery-2', 'QUEUED')
        lease2 = kernel.claim('task-forgery-2', 'worker-1', ttl_seconds=30)
        kernel.start('task-forgery-2', lease2.lease_id)
        # Note: State is still RUNNING! Not even VERIFYING!
        res2 = kernel.commit_completed('task-forgery-2', lease2.lease_id, 'VERIFIED', 'fake://direct-commit')
        print('Variant 2 (Bypass VERIFYING state):', res2['state'])
    finally:
        kernel.close()
"
```

### Raw Observed Output:
```text
VULNERABILITY PROVEN:
Task State: COMPLETED
Journal valid: True
Journal event count: 8
Variant 2 (Bypass VERIFYING state): COMPLETED
```

### Recorded SQLite Event Journal Inspection:
```text
event_id: evt_ecec22f292a27f935dd4dc67
task_id: t1
seq: 8
type: TASK_COMPLETED
from_state: VERIFYING
to_state: COMPLETED
actor: verifier
reason: postcondition_verified
payload_json: {"evidence_ref": "fake", "lease_id": "lease_c15e7a5c1f2eef1ab2941d48", "verifier_verdict": "VERIFIED"}
policy_hash: None
event_hash: sha256:c30cd04f939b06f3d30be050ba68eaec043d8a8331149adccafe6891abb72a38
```

### Exploit Findings Summary:
1. **Unauthenticated Acceptance:** `commit_verification_result()` accepts any arbitrary dictionary with `"verdict": "VERIFIED"` and non-empty `"verifier_id"` and `"evidence_ref"`. No cryptographic signature is checked.
2. **Direct Completion Bypass:** `commit_completed()` can be called directly without a receipt object.
3. **State Machine Bypass:** `commit_completed()` permits `RUNNING -> COMPLETED`, skipping `VERIFYING`.
4. **Masquerading Audit Trail:** The event journal records `actor: "verifier"` even though the caller was a rogue worker.

---

## 4. Architectural Cryptographic Signature / HMAC Scheme Design

To completely eliminate provenance forgery and satisfy R3, a cryptographic receipt verification system modeled after `verify_approval_authority` (GAP-13) and `CapabilityToken` (GAP-08) must be implemented.

### 4.1 Secret Authority & Key Management
- Environment variable: `SCP_VERIFIER_SECRET`.
- Fallback: `SCP_CAPABILITY_SECRET` via `get_verifier_secret()`:
  ```python
  def get_verifier_secret() -> bytes:
      secret = os.environ.get("SCP_VERIFIER_SECRET") or os.environ.get("SCP_CAPABILITY_SECRET")
      if not secret or not str(secret).strip():
          from scp.core.capability_token import MissingSecretError
          raise MissingSecretError(
              "SCP_VERIFIER_SECRET or SCP_CAPABILITY_SECRET environment variable is required "
              "to cryptographically sign and verify verifier receipts (R3/GAP-14)."
          )
      return secret.strip().encode("utf-8")
  ```

### 4.2 Canonical Serialization (Deterministic & Non-Malleable)
To prevent delimiter injection or field tampering (even if `task_id` or `evidence_ref` contain special characters or colons), canonical bytes are constructed using sorted JSON with a distinct cryptographic domain separator:
```python
def canonical_receipt_bytes(
    task_id: str,
    verifier_id: str,
    verdict: str,
    evidence_ref: str,
    issued_at: float,
) -> bytes:
    payload = {
        "domain": "scp.verifier.receipt.v1",
        "evidence_ref": str(evidence_ref).strip(),
        "issued_at": f"{float(issued_at):.6f}",
        "task_id": str(task_id).strip(),
        "verdict": str(verdict).strip(),
        "verifier_id": str(verifier_id).strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

### 4.3 Verifier Receipt Data Structure
```python
@dataclass(frozen=True)
class VerifierReceipt:
    task_id: str
    verifier_id: str
    verdict: str
    evidence_ref: str
    issued_at: float
    signature: str
    attempt_id: str | None = None
```

### 4.4 Signing Algorithm (`sign_verifier_receipt`)
Executed only by authorized Verifier components (`IndependentVerifier`, `RealityJudge` verifier adapter):
```python
def sign_verifier_receipt(
    secret: bytes,
    task_id: str,
    verifier_id: str,
    verdict: str,
    evidence_ref: str,
    issued_at: float | None = None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    ts = time.time() if issued_at is None else float(issued_at)
    canonical = canonical_receipt_bytes(task_id, verifier_id, verdict, evidence_ref, ts)
    signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return {
        "task_id": str(task_id).strip(),
        "verifier_id": str(verifier_id).strip(),
        "verdict": str(verdict).strip(),
        "evidence_ref": str(evidence_ref).strip(),
        "issued_at": ts,
        "signature": signature,
        "attempt_id": attempt_id,
    }
```

### 4.5 Verification Algorithm (`verify_verifier_receipt`)
Executed by `TaskKernel` fail-closed:
```python
def verify_verifier_receipt(
    receipt: Any,
    task_id: str,
    secret: bytes,
    max_skew_seconds: float = 300.0,
) -> dict[str, Any]:
    if not receipt:
        raise InvalidTokenSignatureError("Verifier receipt is missing or empty (R3/FA-04)")
    if hasattr(receipt, "__dataclass_fields__"):
        receipt = asdict(receipt)
    if not isinstance(receipt, dict):
        raise InvalidTokenSignatureError("Verifier receipt must be a dictionary or dataclass")

    receipt_task_id = str(receipt.get("task_id", "")).strip()
    if receipt_task_id != task_id:
        raise InvalidTokenSignatureError(
            f"Receipt task_id '{receipt_task_id}' does not match expected task_id '{task_id}'"
        )

    verifier_id = str(receipt.get("verifier_id", "")).strip()
    if not verifier_id:
        raise InvalidTokenSignatureError("Verifier receipt missing verifier_id")

    verdict = str(receipt.get("verdict", "")).strip()
    if verdict != "VERIFIED":
        raise InvalidTransition(f"Completion requires verifier verdict 'VERIFIED', got '{verdict}'")

    evidence_ref = str(receipt.get("evidence_ref", "")).strip()
    if not evidence_ref:
        raise InvalidTokenSignatureError("Verifier receipt missing evidence_ref")

    sig = str(receipt.get("signature", "")).strip()
    if not sig:
        raise InvalidTokenSignatureError("Verifier receipt is unsigned (R3/FA-04)")

    try:
        issued_at = float(receipt.get("issued_at", 0.0))
    except (TypeError, ValueError):
        raise InvalidTokenSignatureError("Invalid timestamp in verifier receipt")

    now = time.time()
    if issued_at > now + 60.0:
        raise InvalidTokenSignatureError("Verifier receipt issued_at is in the future")
    if now - issued_at > max_skew_seconds:
        raise InvalidTokenSignatureError("Verifier receipt has expired")

    canonical = canonical_receipt_bytes(task_id, verifier_id, verdict, evidence_ref, issued_at)
    expected_sig = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise InvalidTokenSignatureError("Verifier receipt signature verification failed (tampered receipt)")

    return {
        "task_id": task_id,
        "verifier_id": verifier_id,
        "verdict": verdict,
        "evidence_ref": evidence_ref,
        "issued_at": issued_at,
        "signature": sig,
        "signature_digest": sig[:16] + "...",
    }
```

### 4.6 TaskKernel Enforcement Protocol
In `TaskKernel.commit_verification_result(task_id, lease_id, verification_result)`:
1. Calls `secret = get_verifier_secret()`.
2. Verifies `receipt_meta = verify_verifier_receipt(verification_result, task_id, secret)`.
3. Calls `self.commit_completed(task_id, lease_id, receipt=receipt_meta)`.

In `TaskKernel.commit_completed(task_id, lease_id, verifier_verdict=None, evidence_ref=None, receipt=None)`:
1. If `receipt` is not already verified, executes `verify_verifier_receipt()`.
2. Enforces state check: `task['state'] == 'VERIFYING'` (removes the `RUNNING` bypass!).
3. Checks lease authority and worker identity.
4. Performs atomic SQLite OCC update.
5. Appends journal event `TASK_COMPLETED`:
   - `actor`: `receipt_meta["verifier_id"]` (actual verifier, not hardcoded stub)
   - `payload`:
     ```python
     {
         "evidence_ref": receipt_meta["evidence_ref"],
         "verifier_id": receipt_meta["verifier_id"],
         "verifier_verdict": receipt_meta["verdict"],
         "signature_digest": receipt_meta["signature_digest"],
         "lease_id": lease_id,
         "issued_at": receipt_meta["issued_at"],
     }
     ```

---

## 5. Peripheral Vulnerabilities Audit (FA-11 Compliance)

In strict accordance with **FA-11 (Mandatory Peripheral Audit & No Blind Eye)**, adjacent state transitions and evidence handling mechanisms were audited:

| Gap ID | Location | Vulnerability Description | Severity | Impact |
|---|---|---|---|---|
| **GAP-P1** | `taskkernel.py:1058` | **State Machine Invariant Breach (`RUNNING -> COMPLETED`):** `commit_completed()` permits `if task['state'] not in {'VERIFYING', 'RUNNING'}`. A task in `RUNNING` skips the `VERIFYING` state completely, violating `ALLOWED_TRANSITIONS["RUNNING"]`. | **HIGH** | State machine corruption; unobserved verification phase. |
| **GAP-P2** | `taskkernel.py:1073` | **Actor Masquerading in Event Journal:** `_append_event` hardcodes `actor='verifier'` without recording `verifier_id`, timestamp, or signature digest. An unauthenticated worker masquerades as an official auditor. | **MEDIUM** | Audit trail spoofing; false forensic evidence. |
| **GAP-P3** | `taskkernel.py:1056` | **Unchecked Lease Worker Identity:** `_assert_lease(lease_id, task_id)` is called without `actor=...`, allowing any entity possessing the lease ID to trigger completion even if actor does not match `lease['worker_id']`. | **MEDIUM** | Cross-worker execution tampering. |
| **GAP-P4** | `task_kernel_bridge.py:465-485` | **Executor/Verifier Dual-Role Conflation:** `TaskKernelHandsBridge` synthesizes `"verifier_id": "hands-kernel-result-verifier-v1"` directly from `result["verification"]["passed"]`, effectively acting as both executor and verifier simultaneously. | **MEDIUM** | Breaks independence contract (DNA #5, #14). |

---

## 6. Implementation Strategy & Blueprints

When implementing R3, the following files will be touched or added:

1. **`scp/core/verifier_receipt.py` (New Module):**
   - Implements `VerifierReceipt`, `canonical_receipt_bytes`, `sign_verifier_receipt`, `verify_verifier_receipt`, `get_verifier_secret`.
2. **`scp/task_kernel_parts/taskkernel.py`:**
   - Import `verify_verifier_receipt`, `get_verifier_secret`.
   - Update `commit_verification_result` to verify receipt cryptographically.
   - Update `commit_completed` to require verified receipt, enforce `task['state'] == 'VERIFYING'`, record `signature_digest` and `verifier_id` in `TASK_COMPLETED` event.
3. **`scp/verifier.py` (`IndependentVerifier`):**
   - Add `sign_receipt(task_id, result, secret=None)` method to produce signed receipts upon verification.
4. **`scp/ask_kernel_adapter.py`:**
   - In `finalize()`, sign verification receipt using `sign_verifier_receipt()` before submitting to `commit_verification_result()`.
5. **`scp/hands/task_kernel_bridge.py`:**
   - Sign receipt using verifier authority before calling `commit_verification_result()`.
6. **Tests:**
   - Update existing tests that call `commit_completed` or `commit_verification_result` with unsigned stubs to use valid signed receipts (or provide a test helper `sign_test_receipt()`).
   - Add comprehensive adversarial tests in `tests/T04_kernel/test_r3_verifier_receipt_forgery.py`:
     - Test unsigned receipt rejection.
     - Test tampered signature rejection.
     - Test tampered verdict/evidence_ref rejection.
     - Test wrong task_id replay rejection.
     - Test expired receipt rejection.
     - Test future timestamp rejection.
     - Test `RUNNING -> COMPLETED` state skip rejection.
     - Test journal event records signature digest and authentic verifier identity.

---

## 7. Causal-Driven Test Coverage Matrix (FA-13 Compliance)

| Branch ID | Causal Flow Branch | Expected Reality Behavior | Planned Test Case |
|---|---|---|---|
| **R3-BR-01** | Valid receipt signed with `secret` submitted to `commit_verification_result()` | Accepted, task transitions `VERIFYING -> COMPLETED` | `test_valid_signed_receipt_completes_task` |
| **R3-BR-02** | Unsigned receipt dictionary submitted to `commit_verification_result()` | Rejected with `InvalidTokenSignatureError` (fail-closed) | `test_unsigned_receipt_rejected_fail_closed` |
| **R3-BR-03** | Tampered signature (bit flip) submitted | Rejected with `InvalidTokenSignatureError` | `test_tampered_signature_rejected` |
| **R3-BR-04** | Tampered verdict (`CONTRADICTED` flipped to `VERIFIED`) | Signature mismatch -> Rejected with `InvalidTokenSignatureError` | `test_tampered_verdict_fails_digest` |
| **R3-BR-05** | Tampered evidence_ref | Signature mismatch -> Rejected with `InvalidTokenSignatureError` | `test_tampered_evidence_ref_fails_digest` |
| **R3-BR-06** | Receipt issued for `task-A` submitted to `task-B` (cross-task replay) | Rejected with `InvalidTokenSignatureError` | `test_cross_task_receipt_replay_rejected` |
| **R3-BR-07** | Expired receipt (`issued_at` older than `max_skew_seconds`) | Rejected with `InvalidTokenSignatureError` | `test_expired_receipt_rejected` |
| **R3-BR-08** | Future timestamp (`issued_at > now + 60s`) | Rejected with `InvalidTokenSignatureError` | `test_future_receipt_rejected` |
| **R3-BR-09** | Direct call to `commit_completed()` without signed receipt | Rejected fail-closed | `test_direct_commit_completed_requires_receipt` |
| **R3-BR-10** | Call to `commit_completed()` from `RUNNING` state (GAP-P1) | Rejected with `InvalidTransition` | `test_running_to_completed_rejected_must_be_verifying` |
| **R3-BR-11** | Journal event inspection after completion | Event has `actor=verifier_id`, `signature_digest`, `issued_at` | `test_journal_preserves_verifier_provenance` |
| **R3-BR-12** | `AskKernelAdapter` end-to-end flow with signed receipt | Response verified, signed, committed to `COMPLETED` | `test_ask_adapter_signs_and_commits_receipt` |
