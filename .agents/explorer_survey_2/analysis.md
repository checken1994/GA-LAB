# Deep Survey & Architectural Analysis: GAP-08 & GAP-09

**Agent**: Explorer 2 (`explorer_survey_2`)  
**Mission**: Comprehensive survey of GAP-08 (CapabilityToken HMAC-SHA256 Signing) and GAP-09 (Eliminating Hardcoded Fallback Secret & Enforcing Fail-Closed Secret Configuration)  
**Date**: 2026-09-07  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_survey_2\`  
**Binding Rules**: Zero-Trust, Fail-Closed, FA-01 through FA-10, SCP DNA (29 Principles)

---

## Executive Summary

1. **GAP-08 (Token Forgery via Missing Cryptographic Signature)**:
   - **Empirical Reality**: In `scp/security/capability_epoch.py`, `CapabilityToken` is currently a plain dataclass (`subject`, `epoch`, `token_id`, `issued_at`) without any cryptographic signature. `CapabilityAuthority.validate()` only compares `token.epoch == state["epoch"]` and `token.subject == required_subject`, both of which are guessable/public.
   - **Vulnerability Confirmed (FA-09 RED)**: An attacker can instantiate `CapabilityToken(subject="hands:pc.write_file", epoch=0, token_id="fake", issued_at=time.time())` or pass an equivalent JSON string; `CapabilityAuthority.validate()` returns `True`, and `HandsExecutor.execute()` executes the unauthorized action.
   - **Subsystem Duality**: `scp/core/capability_token.py` contains string-based tokens (`mint_token`/`verify_token`) with HMAC signing, while `scp/security/capability_epoch.py` contains the dataclass `CapabilityToken` used by `HandsExecutor`, `TaskKernelHandsBridge`, and `os_sandbox`. These two subsystems were never cryptographically bridged.
   - **Remediation**: Add `signature: str` to `CapabilityToken`, compute HMAC-SHA256 over a canonical payload in `CapabilityAuthority.issue()`, verify in `CapabilityAuthority.validate()`, raise `InvalidTokenSignatureError(PermissionError)` on unsigned or tampered tokens, and strictly reject legacy unsigned tokens (no silent acceptance).

2. **GAP-09 (Hardcoded Fallback Secret in Production Path)**:
   - **Empirical Reality**: In `scp/core/capability_token.py`, lines 14–16 fallback to `b"dev-secret-do-not-use-in-prod-12345"` if `SCP_CAPABILITY_SECRET` is unset.
   - **Vulnerability Confirmed (FA-09 RED)**: Live execution proved that when `SCP_CAPABILITY_SECRET` is unset, the module silently initializes with the hardcoded secret, allowing any external actor to forge valid tokens using this public secret.
   - **Import Sequence Impact**: `scp.core.capability_token` is imported transitively by `scp.hands.planner`, `scp.api.routes.hands_routes`, `scp.api_server`, `scp.core.agent_orchestrator`, and test suites. Raising `MissingSecretError` at module import time requires injecting `SCP_CAPABILITY_SECRET` into `tests/conftest.py` before pytest test collection.
   - **Remediation**: Eliminate the fallback secret; raise `MissingSecretError` if `SCP_CAPABILITY_SECRET` is missing; create `.env.example` at root and update `deploy/vps/scp.env.example`; add root `tests/conftest.py` to safeguard pytest collection.

---

## 1. GAP-08: CapabilityToken HMAC Signing Analysis

### 1.1 Codebase Reality vs Architectural Model

The project currently has two parallel capability modules:
1. **`scp/security/capability_epoch.py`**:
   - Declares `@dataclass(frozen=True) class CapabilityToken:` with fields:
     - `subject: str`
     - `epoch: int`
     - `token_id: str`
     - `issued_at: float`
   - Managed by `CapabilityAuthority`:
     - `issue(subject: str) -> CapabilityToken`
     - `validate(token: CapabilityToken | None, required_subject: str | None = None) -> bool`
   - Parsed by `parse_capability_token(token: Any) -> CapabilityToken | None`
   - **Critical Defect**: Neither `CapabilityToken`, `CapabilityAuthority.issue()`, nor `CapabilityAuthority.validate()` performs any cryptographic signing or verification.

2. **`scp/core/capability_token.py`**:
   - Contains utility functions:
     - `mint_token(issuer: str, scope: str, capability_level: int, ttl_seconds: int = 3600) -> str`
     - `verify_token(token: str, required_scope: str = "*") -> dict`
   - Serializes as `{payload_b64}.{signature}`.
   - Tested by `tests/T03_capability/test_capability_token_mutation_contract.py`.
   - **Critical Defect**: Uses the hardcoded fallback secret `b"dev-secret-do-not-use-in-prod-12345"` and is not bound to the `CapabilityToken` dataclass.

### 1.2 Full Call Graph & Execution Trace

The execution trace demonstrates how capability tokens flow through SCP:

```
[External Caller / Client]
       │
       ▼ (HTTP POST /v3/hands/run, /v3/hands/execute, /v3/hands/rollback)
[scp/api/routes/hands_routes.py]
       │  Extracts payload.capabilityToken (dict, str, or None)
       ▼
[scp/hands/planner.py (HandsPlanner)]
       │  Lines 472-477, 588-593, 743-747:
       │  parsed_step_token = parse_capability_token(step_token)
       │  token_is_valid = (
       │      parsed_step_token is not None
       │      or (isinstance(step_token, str) and "." in step_token and verify_token(step_token).get("valid", False))
       │  )
       ▼
[scp/hands/task_kernel_bridge.py (TaskKernelHandsBridge)]
       │  Line 75: parsed = parse_capability_token(capability_token)
       │  Dispatches to HandsExecutor with capability_token=parsed
       ▼
[scp/hands/hands_executor.py (HandsExecutor - Policy Enforcement Point)]
       │  Line 110: if capability_token is None -> CapabilityRequiredError (FA-05)
       │  Line 121: if capability_token.subject != f"hands:{action}" -> CapabilityScopeMismatchError (INV-AUTH-02)
       │  Line 136: _check_capability(...)
       │       └── Line 69: if not self.capability_authority.validate(capability_token, required_subject=...) -> Denied
       │  Line 146: Pre-dispatch TOCTOU check:
       │       └── if not self.capability_authority.validate(capability_token, required_subject=expected_subject) -> Denied
       ▼
[scp/security/capability_epoch.py (CapabilityAuthority)]
       │  Line 158: validate(token, required_subject)
       │  Checks:
       │    1. token is not None
       │    2. hasattr(token, "subject") and hasattr(token, "epoch")
       │    3. token.subject == required_subject
       │    4. token.epoch == state["epoch"] and not state["revoked"]
       │  *CRITICAL FLAW*: No cryptographic signature check!
       ▼
[scp/security/os_sandbox.py (ProcessIsolationEnvironment)]
       │  Line 167: if not self.authority.validate(capability_token): raise PermissionError
       │  Executes bounded subprocess inside Windows Job Object
```

### 1.3 HMAC-SHA256 Signing Requirements

To remediate GAP-08 in accordance with Zero-Trust:
1. **Signature Field**:
   - `CapabilityToken` must include `signature: str = ""`.
   - `to_dict()` must serialize `"signature": self.signature`.
   - `parse_capability_token()` must parse `"signature": str(token.get("signature") or "")`.
2. **Canonical Payload Representation**:
   - To eliminate whitespace or serialization divergence across platforms:
     - Formatted string canonicalization:
       `payload_bytes = f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")`
     - OR Sorted JSON canonicalization:
       `payload_bytes = json.dumps({"epoch": int(epoch), "issued_at": float(issued_at), "subject": str(subject), "token_id": str(token_id)}, sort_keys=True, separators=(",", ":")).encode("utf-8")`
     - Recommended: `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")` provides maximum determinism without floating-point formatting drift or JSON key variance.
3. **Signature Calculation Algorithm**:
   - `signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()`
4. **Signature Verification**:
   - Verification MUST use constant-time comparison: `hmac.compare_digest(token.signature, expected_signature)`.
5. **Secret Key Handling**:
   - The secret key must be retrieved securely from `SCP_CAPABILITY_SECRET` via `get_capability_secret()`.
   - `CapabilityAuthority` initializes or retrieves this secret during construction/operation.

### 1.4 Error Classes & Fail-Closed Enforcement

- **`InvalidTokenSignatureError`**:
  ```python
  class InvalidTokenSignatureError(PermissionError):
      """Raised when a capability token is unsigned, has an invalid signature, or has been tampered with."""
  ```
  *Why inherit from `PermissionError`?*
  Existing callers (e.g. `test_os_sandbox.py:27`) expect `with pytest.raises(PermissionError): pie.execute_bounded(forged, ...)`. Inheriting from `PermissionError` satisfies existing contracts while introducing exact type specificity.
- **Fail-Closed Rejection**:
  - **Unsigned tokens**: `if not token.signature:` -> immediately raise `InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")`.
  - **Tampered tokens**: If `token.signature != expected_signature` -> raise `InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")`.
  - **Backward Compatibility**: Tokens without a valid HMAC signature MUST be rejected fail-closed. Silently accepting unsigned tokens is strictly forbidden (FA-01 / FA-04).

---

## 2. GAP-09: Eliminating Hardcoded Fallback Secret Analysis

### 2.1 Location of Hardcoded Secret

- **Exact File**: `scp/core/capability_token.py`
- **Lines 11–17**:
  ```python
  _SECRET_STR = os.environ.get("SCP_CAPABILITY_SECRET")
  _SECRET = _SECRET_STR.encode() if _SECRET_STR else b""

  if not _SECRET:
      logger.warning("SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.")
      _SECRET = b"dev-secret-do-not-use-in-prod-12345"
  ```
- **Repo-wide Scan**: A search across the entire repository confirmed that `dev-secret-do-not-use-in-prod-12345` appears nowhere else in the codebase.

### 2.2 Module Import Sequence & Fail-Closed Strategy

- **Import Chain**:
  ```
  scp.api_server
    └── scp.api.routes.hands_routes
          └── scp.hands.planner
                └── scp.core.capability_token
  ```
- If `SCP_CAPABILITY_SECRET` is not set:
  - Current Behavior: Logs a warning and uses the hardcoded secret.
  - Required Behavior: Raise `MissingSecretError` immediately when the secret is accessed or at module initialization.
- **Error Class Definition**:
  ```python
  class MissingSecretError(RuntimeError):
      """Raised when SCP_CAPABILITY_SECRET is missing or empty in the environment."""
  ```
- **Fail-Closed Execution**:
  ```python
  def get_capability_secret() -> bytes:
      secret = os.environ.get("SCP_CAPABILITY_SECRET")
      if not secret or not secret.strip():
          raise MissingSecretError(
              "SCP_CAPABILITY_SECRET environment variable is missing or empty. "
              "A cryptographic secret is required to sign and verify capability tokens (GAP-09)."
          )
      return secret.strip().encode("utf-8")
  ```
  At module top level:
  ```python
  _SECRET = get_capability_secret()
  ```
  This guarantees that no service can start, no token can be minted, and no route can be mounted without an explicit secret.

### 2.3 Environment Loading & Configuration Files

1. **Current State**:
   - Repo root: `.env.example` DOES NOT EXIST.
   - `deploy/vps/scp.env.example`: Exists, but does NOT define `SCP_CAPABILITY_SECRET`.
   - `python-dotenv`: Installed in `scp/requirements.txt`, but loaded selectively (e.g. `scp/__main__.py`).
2. **Remediation**:
   - Create `.env.example` at repo root with explicit instructions:
     ```bash
     # SCP Capability Signing Secret (Required for GAP-08 & GAP-09)
     # Must be a secure random secret of at least 32 characters.
     # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
     SCP_CAPABILITY_SECRET=replace_with_a_secure_random_secret_at_least_32_chars
     ```
   - Update `deploy/vps/scp.env.example` to also include `SCP_CAPABILITY_SECRET`.

### 2.4 Test Suite Impact & Fixture Strategy

- **The Pytest Collection Dilemma**:
  - When `pytest` runs, it collects tests by importing every test file before executing any test function.
  - Because `test_api_import_order_contract.py`, `test_god_split_semantic_parity.py`, `test_hands_authority_pep.py`, and `test_capability_token_mutation_contract.py` all transitively import `capability_token`, if `SCP_CAPABILITY_SECRET` is missing during collection, `pytest` will crash before running tests.
  - `tools/t00_meta_audit.py` also runs `pytest --collect-only -q` in a subprocess.
- **The Solution (Zero Regression, Fail-Closed)**:
  - **Create `tests/conftest.py`**:
    ```python
    import os
    # Ensure test runner has a deterministic test capability secret during suite collection
    os.environ.setdefault(
        "SCP_CAPABILITY_SECRET",
        "test-capability-secret-for-automated-suites-only-32bytes"
    )
    ```
    Because pytest loads `tests/conftest.py` before collecting any test files in `tests/`, this prevents import crashes across all 483 collected tests.
  - **For Negative Tests (Testing MissingSecretError)**:
    Use `monkeypatch.delenv("SCP_CAPABILITY_SECRET", raising=False)` and `importlib.reload(capability_token)` inside a test to verify that `MissingSecretError` is raised when the secret is absent.

---

## 3. Exploit Mandate (FA-09) Evidence Summary

An adversarial probe was executed at `.agents/explorer_survey_2/probe_gap08_gap09.py`.

### 3.1 Terminal Output Evidence

```
Command: python .agents/explorer_survey_2/probe_gap08_gap09.py

SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.
SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.

--- Testing GAP-08: Token Forgery Without Cryptographic Signature ---
Attacker forged token: CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='unauthorized_attacker_id_999', issued_at=1788782810.693538)
cap_auth.validate(forged_token) result: True
>>> [VULNERABILITY CONFIRMED - RED]: CapabilityAuthority accepted an unsigned, forged token!

--- Testing GAP-09: Hardcoded Fallback Secret When Env Var Unset ---
Loaded secret when SCP_CAPABILITY_SECRET is unset: b'dev-secret-do-not-use-in-prod-12345'
>>> [VULNERABILITY CONFIRMED - RED]: scp.core.capability_token used hardcoded dev-secret fallback!

Summary:
GAP-08 Unsigned Forgery Vulnerable: True
GAP-09 Fallback Secret Vulnerable:   True

Both GAP-08 and GAP-09 vulnerabilities strictly confirmed via live terminal execution (FA-09 SATISFIED).
```

### 3.2 Anti-Placebo Post-Fix Validation Plan

When the implementer applies the fix:
1. Running `probe_gap08_gap09.py` must turn GREEN:
   - Forged token -> raises `InvalidTokenSignatureError` (rejected).
   - Missing secret -> raises `MissingSecretError` (fail-closed).
2. Existing 7 tests in `tests/T03_capability/test_capability_token_mutation_contract.py` must continue to PASS.
3. Total suite test count must be >= 450 tests PASS with exit code 0.
4. `python tools/t00_meta_audit.py` must pass with 0 new regressions.

---

## 4. Implementation Blueprint for Implementers

### 4.1 Changes to `scp/core/capability_token.py`

```python
import hmac
import hashlib
import json
import time
import base64
import os
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

class MissingSecretError(RuntimeError):
    """Raised when SCP_CAPABILITY_SECRET is missing or empty in the environment."""

class InvalidTokenSignatureError(PermissionError):
    """Raised when a capability token is unsigned, has an invalid signature, or has been tampered with."""

def get_capability_secret() -> bytes:
    secret = os.environ.get("SCP_CAPABILITY_SECRET")
    if not secret or not secret.strip():
        raise MissingSecretError(
            "SCP_CAPABILITY_SECRET environment variable is missing or empty. "
            "A cryptographic secret is required to sign and verify capability tokens (GAP-09)."
        )
    return secret.strip().encode("utf-8")

# Fail-closed module initialization
_SECRET = get_capability_secret()

def compute_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float) -> str:
    canonical = f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()

def verify_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float, signature: str) -> bool:
    if not signature:
        raise InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")
    expected = compute_token_signature(secret, subject, epoch, token_id, issued_at)
    if not hmac.compare_digest(signature, expected):
        raise InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")
    return True

# Keep existing mint_token and verify_token for backwards compatibility with JWT-like callers
def mint_token(issuer: str, scope: str, capability_level: int, ttl_seconds: int = 3600) -> str:
    ...

def verify_token(token: str, required_scope: str = "*") -> dict:
    ...
```

### 4.2 Changes to `scp/security/capability_epoch.py`

1. Update `CapabilityToken`:
   ```python
   from scp.core.capability_token import (
       InvalidTokenSignatureError,
       compute_token_signature,
       verify_token_signature,
       get_capability_secret,
   )

   @dataclass(frozen=True)
   class CapabilityToken:
       subject: str
       epoch: int
       token_id: str
       issued_at: float
       signature: str = ""

       def to_dict(self) -> dict[str, Any]:
           return {
               "subject": self.subject,
               "epoch": self.epoch,
               "token_id": self.token_id,
               "issued_at": self.issued_at,
               "signature": self.signature,
           }
   ```
2. Update `parse_capability_token`:
   ```python
   # In parse_capability_token, extract signature:
   signature = str(token.get("signature") or "")
   return CapabilityToken(
       subject=subject,
       epoch=epoch,
       token_id=token_id,
       issued_at=issued_at,
       signature=signature,
   )
   ```
3. Update `CapabilityAuthority`:
   - Store secret in `__init__`: `self.secret = get_capability_secret()`
   - In `issue(subject: str) -> CapabilityToken`:
     ```python
     token_id = uuid.uuid4().hex
     issued_at = time.time()
     sig = compute_token_signature(self.secret, subject, state["epoch"], token_id, issued_at)
     return CapabilityToken(
         subject=subject,
         epoch=state["epoch"],
         token_id=token_id,
         issued_at=issued_at,
         signature=sig,
     )
     ```
   - In `validate(token: CapabilityToken | None, required_subject: str | None = None) -> bool`:
     ```python
     if token is None:
         return False
     if not (hasattr(token, "subject") and hasattr(token, "epoch")):
         return False
     # Strict Fail-Closed Signature Verification (GAP-08)
     signature = getattr(token, "signature", "")
     verify_token_signature(
         self.secret,
         str(token.subject),
         int(token.epoch),
         str(getattr(token, "token_id", "")),
         float(getattr(token, "issued_at", 0.0)),
         signature,
     )
     if required_subject is not None:
         if str(getattr(token, "subject", "")) != str(required_subject):
             return False
     with self._lock:
         state = self._load()
         return not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]
     ```

### 4.3 Environment & Fixture Changes

1. **Create `tests/conftest.py`**:
   Sets default `SCP_CAPABILITY_SECRET` to prevent import crashes during test collection.
2. **Create `.env.example`** at repository root with `SCP_CAPABILITY_SECRET`.
3. **Update `deploy/vps/scp.env.example`** with `SCP_CAPABILITY_SECRET`.
4. **Add Dedicated Unit Tests**:
   - `test_capability_token_unsigned_rejected`: verifies `InvalidTokenSignatureError`.
   - `test_capability_token_tampered_rejected`: verifies signature mismatch rejection.
   - `test_capability_token_missing_secret_fails_closed`: verifies `MissingSecretError` on reload with unset env var.
   - `test_capability_token_roundtrip_verified`: verifies legitimate signed tokens pass validation.
