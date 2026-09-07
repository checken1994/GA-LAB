# Worker M3 Dispatch: Milestone 3 (GAP-08) CapabilityToken HMAC Signing & Validation

- Working Directory: c:\Users\check\Downloads\scp\.agents\worker_m3
- Authoritative User Request: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
- Project Scope: c:\Users\check\Downloads\scp\.agents\orchestrator_7\PROJECT.md
- Survey Reference: c:\Users\check\Downloads\scp\.agents\explorer_survey_2\analysis.md
- Milestone 2 Reference: c:\Users\check\Downloads\scp\.agents\worker_m2\handoff.md

## Exclusive Write Ownership
- `scp/core/capability_token.py`
- `scp/security/capability_epoch.py`
- `tests/T03_capability/test_capability_token_hmac_signing.py`
- `tests/T03_capability/test_os_sandbox.py` (only if updating to use genuine issued tokens while preserving test strictness)
- `.agents/worker_m3/*`

## Tasks
1. Run Anti-Placebo RED Probe for GAP-08:
   - Construct an unsigned or forged `CapabilityToken` and verify that `CapabilityAuthority.validate()` currently fails to check cryptographic signatures (returns True or doesn't verify HMAC).
2. Implement Milestone 3 (GAP-08):
   - In `scp/core/capability_token.py`:
     * Define `class InvalidTokenSignatureError(PermissionError): ...`
     * Implement canonical signature computation:
       `compute_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float) -> str`
       Using `hmac.new(secret, f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8"), hashlib.sha256).hexdigest()`.
     * Implement signature verification:
       `verify_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float, signature: str) -> bool`
       Must raise `InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")` if `signature` is empty or missing.
       Must raise `InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")` if `hmac.compare_digest(signature, expected)` is False.
     * Re-export `CapabilityToken` if appropriate.
   - In `scp/security/capability_epoch.py`:
     * Add `signature: str = ""` field to `CapabilityToken` dataclass.
     * Update `CapabilityToken.to_dict()` to include `"signature": self.signature`.
     * Update `parse_capability_token()` to extract `"signature"`.
     * In `CapabilityAuthority.__init__()`, initialize secret via `get_capability_secret()` (or accept optional secret).
     * In `CapabilityAuthority.issue(subject: str) -> CapabilityToken`:
       Generate token, compute HMAC-SHA256 signature using `self.secret`, and return `CapabilityToken` with signature attached.
     * In `CapabilityAuthority.validate(token: CapabilityToken | None, required_subject: str | None = None) -> bool`:
       If `token is None: return False`.
       If `not (hasattr(token, "subject") and hasattr(token, "epoch")): return False`.
       Perform strict fail-closed signature verification via `verify_token_signature(...)` (raising `InvalidTokenSignatureError` on missing or invalid signature).
       Then verify `epoch == state["epoch"]` and `required_subject`.
   - Write comprehensive test suite in `tests/T03_capability/test_capability_token_hmac_signing.py`:
     * Test legitimate token `issue()` produces valid HMAC signature.
     * Test `validate()` accepts legitimately issued tokens.
     * Test unsigned token (missing signature) raises `InvalidTokenSignatureError`.
     * Test forged token with random signature raises `InvalidTokenSignatureError`.
     * Test tampered subject/epoch/token_id/issued_at raises `InvalidTokenSignatureError`.
     * Test token signed with wrong secret raises `InvalidTokenSignatureError`.
     * Test backward compatibility: old tokens without signature are strictly REJECTED (fail-closed).
   - If any existing tests (like `test_os_sandbox.py`) need legitimate tokens, ensure they use `authority.issue()` while preserving all security assertions.
3. Run Anti-Placebo GREEN Probe:
   - Confirm forged and unsigned tokens are strictly rejected with `InvalidTokenSignatureError`.
4. Run full test verification:
   - `pytest tests/T03_capability/ -v`
   - `pytest tests/ -q` (>= 477 tests PASS, exit 0)
   - `python tools/t00_meta_audit.py` (0 regressions)
5. Deliver handoff report to `c:\Users\check\Downloads\scp\.agents\worker_m3\handoff.md`.

## 2026-09-07T12:40:34Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker M3 (teamwork_preview_worker).
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_m3
Your task assignment is detailed at: c:\Users\check\Downloads\scp\.agents\worker_m3\DISPATCH.md
Read the authoritative user request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Read project context at: c:\Users\check\Downloads\scp\.agents\orchestrator_7\PROJECT.md
Read survey blueprint at: c:\Users\check\Downloads\scp\.agents\explorer_survey_2\analysis.md
Read worker m2 handoff at: c:\Users\check\Downloads\scp\.agents\worker_m2\handoff.md
Read skill instructions at: c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md and c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md

Exclusive Write Ownership:
- scp/core/capability_token.py
- scp/security/capability_epoch.py
- tests/T03_capability/test_capability_token_hmac_signing.py
- tests/T03_capability/test_os_sandbox.py (only if updating to use genuine issued tokens while preserving strictness)
- .agents/worker_m3/*

Tasks:
1. Run Anti-Placebo RED Probe for GAP-08:
   - Construct an unsigned/forged CapabilityToken and demonstrate that CapabilityAuthority.validate() currently accepts it without signature verification.
2. Implement Milestone 3 (GAP-08):
   - In `scp/core/capability_token.py`:
     * Define `class InvalidTokenSignatureError(PermissionError): ...`
     * Implement `compute_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float) -> str`
     * Implement `verify_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float, signature: str) -> bool` using constant-time `hmac.compare_digest`. Raise `InvalidTokenSignatureError` fail-closed on missing or invalid signature.
     * Re-export CapabilityToken from scp.security.capability_epoch if appropriate.
   - In `scp/security/capability_epoch.py`:
     * Add `signature: str = ""` field to `CapabilityToken` dataclass.
     * Update `to_dict()` and `parse_capability_token()`.
     * In `CapabilityAuthority.__init__()`, initialize `self.secret = get_capability_secret()` (allowing optional secret override).
     * In `CapabilityAuthority.issue(subject: str) -> CapabilityToken`, compute and attach HMAC signature.
     * In `CapabilityAuthority.validate(token: CapabilityToken | None, required_subject: str | None = None) -> bool`:
       If token is None: return False.
       Verify HMAC signature via `verify_token_signature(...)` (raises `InvalidTokenSignatureError` fail-closed if signature is missing, invalid, or forged).
       Check required_subject and epoch as before.
   - Write comprehensive unit tests in `tests/T03_capability/test_capability_token_hmac_signing.py` covering:
     * Legitimate issue & validate roundtrip.
     * Unsigned token rejected with `InvalidTokenSignatureError`.
     * Tampered signature rejected with `InvalidTokenSignatureError`.
     * Tampered subject/epoch/token_id rejected with `InvalidTokenSignatureError`.
     * Token signed with wrong secret rejected with `InvalidTokenSignatureError`.
     * Legacy token without signature rejected (no silent acceptance).
   - If tests in `test_os_sandbox.py` or other tests construct dummy tokens, update them so legitimate calls use `authority.issue()` while preserving test strictness and security checks.
3. Run Anti-Placebo GREEN Probe:
   - Prove that forged tokens are now blocked with `InvalidTokenSignatureError`.
4. Run full test suites:
   - `pytest tests/T03_capability/ -v`
   - `pytest tests/ -q` (>= 477 tests PASS, exit code 0)
   - `python tools/t00_meta_audit.py` (0 regressions)
5. Deliver comprehensive handoff report to `c:\Users\check\Downloads\scp\.agents\worker_m3\handoff.md` and notify parent via send_message.
