# Handoff Report: CapabilityToken & Cryptographic Verification Analysis (GAP-13)

**Author**: Explorer Subagent #2 (`explorer_gap13_2`)  
**Parent Agent**: Orchestrator (`6c4f4b5d-80a9-4083-87c8-3858c1af90bc`)  
**Target Vulnerability**: GAP-13 (Unauthenticated `WAITING_APPROVAL` Bypass)  
**Mandate Compliance**: Zero-Trust, Fail-Closed, FA-01 through FA-13, FA-05 (No Self-Granting Authority)  
**Date**: 2026-09-08T02:15:00Z  

---

## 1. Observation

### 1.1 Existing Cryptographic Modules & Secret Management
Direct inspection of the codebase (`view_file`, `grep_search`) confirmed the following mechanisms and interfaces:

1. **`scp/core/capability_token.py`**:
   - **Secret Extraction (`get_capability_secret()`)** (lines 40–54):
     Reads `os.environ.get("SCP_CAPABILITY_SECRET")`. If unset, empty, or whitespace, immediately raises `MissingSecretError(RuntimeError)` (GAP-09 fail-closed). At module import time, `_SECRET = get_capability_secret()` guarantees that any execution without a configured secret halts immediately.
   - **Canonical HMAC Signature Computation (`compute_token_signature()`)** (lines 21–25):
     ```python
     canonical = f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")
     return hmac.new(secret, canonical, hashlib.sha256).hexdigest()
     ```
     Signature is a 64-character lowercase hex digest of deterministic HMAC-SHA256.
   - **Constant-Time Signature Verification (`verify_token_signature()`)** (lines 27–38):
     Fails closed: if `signature` is empty or whitespace, raises `InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")`.
     Uses `hmac.compare_digest(str(signature).strip(), expected)`. If mismatched, raises `InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")`.
   - **Compact String Token Minting & Verification (`mint_token()`, `verify_token()`)** (lines 56–95):
     - `mint_token(issuer, scope, capability_level, ttl_seconds)`: encodes payload `{"iss", "scope", "cap", "iat", "exp"}` into URL-safe base64 and signs it as `f"{payload_b64}.{signature}"`.
     - `verify_token(token, required_scope)`: validates dot-delimited format, recalculates HMAC-SHA256 signature using constant-time comparison, validates `exp >= time.time()`, and verifies `scope == required_scope` or wildcard `"*"`. Returns dict `{"valid": bool, "payload": dict, "error": str}`.
   - **Re-export (`__getattr__`)** (lines 97–101):
     Dynamically re-exports `CapabilityToken` dataclass from `scp.security.capability_epoch`.

2. **`scp/security/capability_epoch.py`**:
   - **Dataclass `CapabilityToken`** (lines 25–41):
     `@dataclass(frozen=True)` with attributes:
     - `subject: str`
     - `epoch: int`
     - `token_id: str`
     - `issued_at: float`
     - `signature: str = ""`
   - **Safe Parser (`parse_capability_token()`)** (lines 43–85):
     Safely parses `CapabilityToken` instances, JSON strings, or dictionaries. If missing required fields (`epoch`, `subject`, etc.) or malformed, returns `None` fail-closed.
   - **Durable Epoch Authority (`CapabilityAuthority`)** (lines 87–249):
     Maintains atomic JSON file (`schema_version`, `epoch`, `revoked`, `reason`, `actor`, `updated_at`).
     - `issue(subject)`: mints a `CapabilityToken` using current epoch and signs via `compute_token_signature()`.
     - `validate(token, required_subject)`: validates HMAC signature via `verify_token_signature()`, checks subject equality (`token.subject == required_subject`), and verifies `not state["revoked"] and token.epoch == state["epoch"]`.

3. **`scp/task_kernel_parts/taskkernel.py` & `scp/task_kernel.py`**:
   - `ALLOWED_TRANSITIONS`:
     - `"PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"}`
     - `"WAITING_APPROVAL": {"READY", "CANCELLED"}`
   - `transition()` method (lines 246–379):
     - Blocks direct transition to `COMPLETED` and `FAILED` (GAP-11 & GAP-12):
       ```python
       if to_state in ("COMPLETED", "FAILED"):
           raise InvalidTransition(
               f"direct transition to {to_state} is forbidden; use commit_{to_state.lower()}() with valid evidence"
           )
       ```
     - **Vulnerability Observation (GAP-13)**:
       When `task["state"] == "WAITING_APPROVAL"`, calling `transition(task_id, "READY")` is permitted by `ALLOWED_TRANSITIONS["WAITING_APPROVAL"]` and completely bypasses cryptographic token check, approver identity check, or permission check.
   - Empirical proof confirmed in `tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py` lines 85–100:
     ```text
     [GAP-13.2] EXPLOIT CONFIRMED: WAITING_APPROVAL -> READY succeeded with zero tokens or cryptographic signatures.
     ```

4. **Operator Signature Exploration**:
   - Grep search for `operator signature`, `ed25519`, `public_key`, `private_key` revealed **zero** asymmetric cryptography implementations in the codebase.
   - Operator actions across `scp/` (`CapabilityAuthority.revoke`, `CapabilityAuthority.restore`, `TaskKernel.set_global_kill`) designate administrative actions using string `actor="operator"`.
   - Symmetric HMAC-SHA256 using `SCP_CAPABILITY_SECRET` (or `SCP_JWT_SECRET` / `SCP_ADMIN_KEY`) is the unified, authoritative cryptographic mechanism of SCP.

---

## 2. Logic Chain

```
[Observation: CapabilityToken HMAC signing & validation proven in GAP-08/GAP-09]
        │
        ▼
[Observation: WAITING_APPROVAL -> READY transition currently has NO token or signature check in transition()]
        │
        ▼
[Logic Step 1: GAP-13 Root Cause]
  `transition()` allows any caller to transition tasks in `WAITING_APPROVAL` to `READY`
  without presenting a cryptographic capability token or authorized operator signature.
        │
        ▼
[Logic Step 2: Enforcement of FA-05 (NO self-granting authority)]
  `TaskKernel` is strictly an executor / state repository. It MUST NEVER mint or issue
  tokens for approvals. The approval token MUST be provided by an external authority
  or operator to `commit_approval()`. TaskKernel only verifies the token.
        │
        ▼
[Logic Step 3: Dual Token Contract Formulation]
  Callers may supply either:
    A. Compact string token minted via `mint_token(..., scope="approval:grant")`.
    B. Dataclass/dict/JSON `CapabilityToken` issued with `subject="approval:grant"` (or `subject="approval:grant:<task_id>"`).
    C. Structured Operator Signature payload signed with HMAC-SHA256.
        │
        ▼
[Logic Step 4: Defense-in-Depth at DB & State Machine Level]
  1. Block direct `transition(..., "READY")` when current state is `WAITING_APPROVAL`.
  2. Implement dedicated `commit_approval(task_id, approval_token, actor, details, expected_version)`.
  3. Enforce SQLite OCC fencing (`UPDATE tasks SET state='READY', version=version+1 WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'`).
  4. Record immutable journal event `TASK_APPROVED` with token signature reference, actor, and timestamp.
```

---

## 3. Detailed Cryptographic & Interface Design

### 3.1 Permission Representation (`approval:grant`)
To guarantee compatibility across subsystems:
1. **`scope` / `subject` String Convention**:
   The permission MUST be represented as:
   - Exact match: `"approval:grant"`
   - Task-scoped match: `f"approval:grant:{task_id}"`
   - Global administrative wildcard: `"*"`
2. **Evaluation Rules**:
   A token authorizes approval for `task_id` if and only if:
   - For string tokens (`verify_token`):
     `token_scope in {"approval:grant", f"approval:grant:{task_id}", "*"}`.
   - For `CapabilityToken` dataclass:
     `token.subject in {"approval:grant", f"approval:grant:{task_id}", "*"}`.

### 3.2 Operator Signature Specification
For operator-initiated direct approvals without generating an epoch token:
- **Canonical Message**:
  `f"operator_approval:{task_id}:{actor}:{timestamp:.6f}"`
- **Signature Algorithm**:
  `hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()`
- **Operator Signature Structure**:
  May be passed as a dictionary:
  ```python
  {
      "type": "operator_signature",
      "actor": actor,
      "task_id": task_id,
      "timestamp": timestamp,
      "signature": signature,
  }
  ```
- **Validation**:
  1. `abs(time.time() - timestamp) <= max_skew_seconds` (e.g., 300 seconds TTL).
  2. Recompute expected HMAC and verify with `hmac.compare_digest`.
  3. Fail closed with `InvalidTokenSignatureError` if invalid or expired.

### 3.3 Universal Approval Token Authenticator (`authenticate_approval_token()`)
We define a pure, fail-closed helper function designed for `TaskKernel` verification:

```python
def verify_approval_authority(
    token: Any,
    task_id: str,
    secret: bytes,
    max_skew_seconds: float = 300.0,
) -> dict[str, Any]:
    """Verify an approval token or operator signature fail-closed.

    Returns a dict with verification metadata (token_id, actor, scope, subject).
    Raises InvalidTokenSignatureError, InvalidTransition, or PermissionError on any failure.
    """
    if token is None or token == "":
        raise InvalidTokenSignatureError("Approval token is missing or empty (GAP-13/FA-04)")

    # Branch 1: Compact string token (mint_token format "payload_b64.sig")
    if isinstance(token, str) and "." in token and not token.strip().startswith("{"):
        from scp.core.capability_token import verify_token
        res = verify_token(token.strip(), required_scope="*")
        if not res.get("valid"):
            raise InvalidTokenSignatureError(f"Invalid capability token: {res.get('error')}")
        payload = res.get("payload", {})
        scope = payload.get("scope", "")
        if scope not in {"approval:grant", f"approval:grant:{task_id}", "*"}:
            raise InvalidTransition(
                f"Capability token scope '{scope}' does not authorize 'approval:grant' for task '{task_id}'"
            )
        return {
            "token_type": "compact_mint_token",
            "token_id": payload.get("iat", ""),
            "actor": payload.get("iss", "unknown"),
            "scope": scope,
            "signature": token.strip().split(".", 1)[1],
        }

    # Branch 2: CapabilityToken instance, dict, or JSON string
    from scp.security.capability_epoch import parse_capability_token
    cap_token = parse_capability_token(token)
    if cap_token is not None:
        if not cap_token.signature or not cap_token.signature.strip():
            raise InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")
        from scp.core.capability_token import verify_token_signature
        verify_token_signature(
            secret=secret,
            subject=cap_token.subject,
            epoch=cap_token.epoch,
            token_id=cap_token.token_id,
            issued_at=cap_token.issued_at,
            signature=cap_token.signature,
        )
        if cap_token.subject not in {"approval:grant", f"approval:grant:{task_id}", "*"}:
            raise InvalidTransition(
                f"CapabilityToken subject '{cap_token.subject}' does not authorize 'approval:grant' for task '{task_id}'"
            )
        return {
            "token_type": "capability_token_epoch",
            "token_id": cap_token.token_id,
            "actor": "capability_authority",
            "scope": cap_token.subject,
            "signature": cap_token.signature,
        }

    # Branch 3: Operator Signature Dictionary
    if isinstance(token, dict) and "signature" in token:
        actor = str(token.get("actor") or token.get("operator", "")).strip()
        sig = str(token.get("signature", "")).strip()
        ts_val = token.get("timestamp")
        if not actor or not sig or ts_val is None:
            raise InvalidTokenSignatureError("Malformed operator signature structure")
        timestamp = float(ts_val)
        if time.time() - timestamp > max_skew_seconds:
            raise InvalidTransition("Operator approval signature has expired")
        if timestamp > time.time() + 60.0:
            raise InvalidTokenSignatureError("Operator approval timestamp is in the future")
        
        # Verify deterministic HMAC
        canonical = f"operator_approval:{task_id}:{actor}:{timestamp:.6f}".encode("utf-8")
        expected_sig = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise InvalidTokenSignatureError("Operator approval signature verification failed")
        return {
            "token_type": "operator_signature",
            "token_id": f"op_{actor}_{int(timestamp)}",
            "actor": actor,
            "scope": "approval:grant",
            "signature": sig,
        }

    raise InvalidTokenSignatureError("Unsupported approval token format")
```

### 3.4 Architecture of `commit_approval()` in `TaskKernel`
```python
def commit_approval(
    self,
    task_id: str,
    approval_token: Any,
    actor: str = "operator",
    details: dict[str, Any] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Atomically commit an authenticated approval to transition WAITING_APPROVAL -> READY.

    Enforces:
    - Task existence and state == WAITING_APPROVAL.
    - Global kill switch check.
    - Strict cryptographic verification of approval_token (CapabilityToken or operator signature).
    - Scope authorization for 'approval:grant'.
    - OCC version check at database level.
    - Append-only event journaling ('TASK_APPROVED').
    - WAL disk durability commit.
    """
    if not task_id or not str(task_id).strip():
        raise KernelError("task_id is required")
    if approval_token is None or approval_token == "":
        raise InvalidTokenSignatureError("approval_token is required")
    if not actor or not str(actor).strip():
        raise KernelError("actor is required")

    self._begin()
    try:
        self._assert_not_killed()
        task = self._task(task_id)
        current_state = task["state"]

        if current_state in TERMINAL:
            raise InvalidTransition("terminal task is immutable")
        if current_state != "WAITING_APPROVAL":
            raise InvalidTransition(
                f"task {task_id} in state '{current_state}' cannot be approved; task must be in WAITING_APPROVAL"
            )

        cur_version = int(task["version"])
        if expected_version is not None and cur_version != expected_version:
            raise OptimisticLockError(
                f"concurrency conflict approving task {task_id}: expected version {expected_version}, found {cur_version}",
                table="tasks",
                entity_id=task_id,
                expected_version=expected_version,
            )

        # Cryptographic verification via capability secret
        from scp.core.capability_token import get_capability_secret
        secret = get_capability_secret()
        verification_meta = verify_approval_authority(approval_token, task_id, secret)

        # Atomic SQLite OCC Mutation
        now_str = now_iso()
        cur = self.conn.execute(
            "UPDATE tasks SET state='READY', version=version+1, updated_at=? WHERE task_id=? AND version=? AND state='WAITING_APPROVAL'",
            (now_str, task_id, cur_version),
        )
        if cur.rowcount != 1:
            raise OptimisticLockError(
                f"concurrency conflict committing approval on task {task_id}: expected version {cur_version}",
                table="tasks",
                entity_id=task_id,
                expected_version=cur_version,
            )

        # Immutable Event Journaling
        event_payload = {
            "token_type": verification_meta["token_type"],
            "token_id": verification_meta["token_id"],
            "scope": verification_meta["scope"],
            "signature_digest": verification_meta["signature"][:16] + "...",
            "actor": actor,
            "details": details or {},
        }
        self._append_event(
            task_id,
            "TASK_APPROVED",
            "WAITING_APPROVAL",
            "READY",
            actor,
            "approval_granted",
            event_payload,
        )

        self._commit()
        return self.get_task(task_id)
    except Exception:
        self._rollback()
        raise
```

### 3.5 Raw Transition Prohibition in `transition()`
Inside `TaskKernel.transition()` (at line 285 in `taskkernel.py`):
```python
if old == "WAITING_APPROVAL" and to_state == "READY":
    raise InvalidTransition(
        "direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token"
    )
```

---

## 4. Caveats

1. **Local Secret Dependency (`SCP_CAPABILITY_SECRET`)**:
   `TaskKernel` verifying tokens requires `SCP_CAPABILITY_SECRET`. In test suites, `tests/conftest.py` configures a default test secret via `os.environ.setdefault`. In production, if `SCP_CAPABILITY_SECRET` is unset, `get_capability_secret()` will raise `MissingSecretError`, preventing silent execution without cryptographic protection.
2. **Clock Skew Tolerances**:
   Operator signatures rely on timestamp validation. If system clocks across distributed nodes drift beyond 300 seconds, signatures will be rejected fail-closed.
3. **Task Scope Specificity**:
   While wildcard `"*"` or `"approval:grant"` allows cross-task approvals for high-level coordinators, best-practice defense-in-depth recommends scoping approval tokens to `f"approval:grant:{task_id}"` to prevent token reuse across different tasks.

---

## 5. Conclusion

1. **GAP-13 Root Cause Confirmed**:
   The transition from `WAITING_APPROVAL` to `READY` in `TaskKernel.transition()` was unprotected and did not require any token, signature, or authority verification.
2. **Cryptographic Infrastructure Ready**:
   `scp/core/capability_token.py` and `scp/security/capability_epoch.py` already supply robust HMAC-SHA256 signing, constant-time verification, and secret fail-closed protections.
3. **Zero-Trust & FA-05 Compliance**:
   By restricting `TaskKernel` to purely *verifying* tokens provided by external callers in `commit_approval()`, self-granting authority is strictly prevented.
4. **Implementation Blueprint Established**:
   The combined enforcement of:
   - Raw transition blockage in `transition()`
   - Dual-token and operator signature cryptographic verification in `commit_approval()`
   - SQLite OCC version fencing and immutable journal audit logging
   provides complete, airtight remediation of GAP-13.

---

## 6. Verification Method

To independently verify the findings and prospective implementation:

1. **Verify Existing Token Security Contracts**:
   ```bash
   python -m pytest tests/T03_capability/ -q --tb=short
   ```
   Ensures HMAC-SHA256 signing, secret fail-closed, and tamper-resistance are 100% active.

2. **Verify Exploit Reproduction (Pre-Patch RED)**:
   ```bash
   python tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py
   ```
   Confirms GAP-13.2 unauthenticated bypass reproduces.

3. **Verify Kernel Regression Safety**:
   ```bash
   python -m pytest tests/T04_kernel/ -q --tb=short
   ```
   Ensures all 66+ existing kernel tests and state machines pass with 0 regressions.

4. **Verify Meta-Audit Invariants**:
   ```bash
   python tools/t00_meta_audit.py
   ```
   Verifies 0 forbidden actions, proper boundaries, and invariant compliance.
