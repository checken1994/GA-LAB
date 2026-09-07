# Handoff Report: Milestone 3 (GAP-08) CapabilityToken HMAC Signing & Validation

**Agent**: Worker M3 (`teamwork_preview_worker`)  
**Parent Agent**: `570b10ff-8aa5-485c-9586-19db62136cd2`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\worker_m3\`  
**Date**: 2026-09-07T19:50:00+07:00 (2026-09-07T12:50:00Z)  
**HEAD SHA**: `bc424a4b45fdf76e0f51fbba62d7bd52dde55e5e`  
**Working Tree Hash**: `044dfcb64b10ebc4494dcd540d36dad78f990afa`  
**Milestone**: M3 (GAP-08 Capability Token HMAC-SHA256 Signing & Anti-Forgery Verification)  
**Standards**: SCP DNA (29 Principles), Zero-Trust, Fail-Closed, FA-01 through FA-10  

---

## 1. Observation

### A. Anti-Placebo RED Probe (Pre-Modification GAP-08 Vulnerability Confirmation)
1. **Command Executed**:
   ```pwsh
   python -c "import tempfile, time; from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken; tmp = tempfile.TemporaryDirectory(); auth = CapabilityAuthority(state_path=tmp.name + '/caps.json'); forged = CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='attacker-forged', issued_at=time.time()); res = auth.validate(forged, required_subject='hands:pc.write_file'); print('VULNERABILITY DETECTED (RED): auth.validate(forged) returned:', res); assert res is True; tmp.cleanup()"
   ```
2. **Verbatim Output**:
   ```
   VULNERABILITY DETECTED (RED): auth.validate(forged) returned: True
   ```
3. **Direct Observation**: An attacker was able to fabricate an arbitrary `CapabilityToken` dataclass with `subject="hands:pc.write_file"`, `epoch=0`, `token_id="attacker-forged"`, and `issued_at=time.time()`, and `CapabilityAuthority.validate()` accepted it without any cryptographic signature verification. This directly violated FA-04 and Zero-Trust.

### B. Changes Made Under Exclusive Write Ownership
1. **`scp/core/capability_token.py`**:
   - Defined exception:
     ```python
     class InvalidTokenSignatureError(PermissionError):
         """Raised when a capability token is unsigned, has an invalid signature, or has been tampered with."""
         pass
     ```
   - Implemented canonical HMAC-SHA256 signature computation:
     ```python
     def compute_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float) -> str:
         canonical = f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")
         return hmac.new(secret, canonical, hashlib.sha256).hexdigest()
     ```
   - Implemented constant-time signature verification:
     ```python
     def verify_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float, signature: str) -> bool:
         if not signature or not str(signature).strip():
             raise InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")
         expected = compute_token_signature(secret, subject, epoch, token_id, issued_at)
         if not hmac.compare_digest(str(signature).strip(), expected):
             raise InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")
         return True
     ```
   - Re-exported `CapabilityToken` via PEP 562 `__getattr__` and `__all__` to ensure non-circular unified module access.

2. **`scp/security/capability_epoch.py`**:
   - Updated `CapabilityToken` dataclass with `signature: str = ""`.
   - Updated `CapabilityToken.to_dict()` to include `"signature": self.signature`.
   - Updated `parse_capability_token()` to extract `"signature"`.
   - Updated `CapabilityAuthority.__init__()` to accept optional `secret: bytes | str | None = None` (falling back to `get_capability_secret()`).
   - Updated `CapabilityAuthority.issue(subject: str) -> CapabilityToken` to compute and attach HMAC-SHA256 signature using `round(time.time(), 6)`.
   - Updated `CapabilityAuthority.validate(token: CapabilityToken | None, required_subject: str | None = None) -> bool` to perform strict fail-closed signature verification via `verify_token_signature(...)` before validating epoch or subject.

3. **`tests/T03_capability/test_capability_token_hmac_signing.py`**:
   - Created 20 comprehensive unit tests covering:
     * `test_invalid_token_signature_error_inherits_permission_error`
     * `test_capability_token_reexported_from_core_and_security`
     * `test_compute_token_signature_deterministic`
     * `test_verify_token_signature_direct_contract`
     * `test_legitimate_token_issue_and_validate_roundtrip`
     * `test_token_dictionary_and_json_roundtrip_preserves_signature`
     * `test_unsigned_token_rejected_fail_closed`
     * `test_none_signature_rejected_fail_closed`
     * `test_tampered_signature_rejected`
     * `test_tampered_subject_rejected`
     * `test_tampered_epoch_rejected`
     * `test_tampered_token_id_rejected`
     * `test_tampered_issued_at_rejected`
     * `test_token_signed_with_wrong_secret_rejected`
     * `test_legacy_unsigned_token_dict_strictly_rejected`
     * `test_legacy_unsigned_token_json_strictly_rejected`
     * `test_revoked_epoch_with_valid_signature_returns_false`
     * `test_subject_mismatch_with_valid_signature_returns_false`
     * `test_none_token_returns_false`
     * `test_invalid_object_returns_false`

### C. Anti-Placebo GREEN Probe (Post-Modification Proof)
1. **Command Executed**:
   ```pwsh
   python -c @"
   import tempfile, time, os
   os.environ['SCP_CAPABILITY_SECRET'] = 'test-secret-32-chars-long-abcdef012345'
   from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken, InvalidTokenSignatureError

   with tempfile.TemporaryDirectory() as tmp:
       auth = CapabilityAuthority(state_path=os.path.join(tmp, 'caps.json'))
       forged = CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='attacker-forged', issued_at=time.time())
       try:
           res = auth.validate(forged, required_subject='hands:pc.write_file')
           print('FAILED: Forged token was accepted!', res)
       except InvalidTokenSignatureError as exc:
           print('SUCCESS: Caught expected InvalidTokenSignatureError on forged unsigned token:', exc)

       # Test tampered signature
       tampered = CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='attacker-forged', issued_at=time.time(), signature='bad-signature-deadbeef')
       try:
           res = auth.validate(tampered, required_subject='hands:pc.write_file')
           print('FAILED: Tampered token was accepted!', res)
       except InvalidTokenSignatureError as exc:
           print('SUCCESS: Caught expected InvalidTokenSignatureError on tampered token:', exc)

       # Test legitimate issued token
       legit = auth.issue('hands:pc.write_file')
       res = auth.validate(legit, required_subject='hands:pc.write_file')
       print('SUCCESS: Legitimate token validated:', res)
       assert res is True
   "@
   ```
2. **Verbatim Output**:
   ```
   SUCCESS: Caught expected InvalidTokenSignatureError on forged unsigned token: Capability token is unsigned (GAP-08/FA-04)
   SUCCESS: Caught expected InvalidTokenSignatureError on tampered token: Capability token signature verification failed (tampered token)
   SUCCESS: Legitimate token validated: True
   ```

### D. Test Suite Verification
1. **New Test Suite**:
   - Command: `pytest tests/T03_capability/test_capability_token_hmac_signing.py -v`
   - Verbatim Output: `20 passed in 0.56s`
2. **Capability Test Directory**:
   - Command: `pytest tests/T03_capability/ -v`
   - Verbatim Output: `85 passed in 1.98s` (All 85 tests PASSED, 0 failures, 0 regressions)
3. **Full Repository Test Suite**:
   - Command: `pytest tests/ -q`
   - Verbatim Output: `497 passed in 112.00s (0:01:52)`, Exit code: 0
4. **Pre-Commit Meta-Audit**:
   - Command: `python tools/t00_meta_audit.py`
   - Verbatim Output:
     ```
     [T00 Meta-Audit] Starting Test-Integrity Regression Authority...
     [T00 Meta-Audit] Trusted Base: origin/main
     ...
     [T00 Meta-Audit] All integrity checks passed (0 new regressions).
     ```

---

## 2. Logic Chain

1. **Vulnerability Analysis (GAP-08)**:
   - *Observation 1.A*: Prior to modification, `CapabilityToken` dataclass lacked a signature field, and `CapabilityAuthority.validate()` only checked epoch equality and subject string match. Both fields were trivially predictable.
   - *Logic*: An unauthenticated attacker or rogue agent could forge arbitrary capability tokens to execute high-privilege tool actions (e.g. `pc.write_file`, shell execution), completely bypassing the Policy Enforcement Point (PEP).
2. **Cryptographic Signing Architecture**:
   - *Observation 1.B.1 & 1.B.2*: `compute_token_signature` constructs a canonical UTF-8 payload `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}"` and computes HMAC-SHA256 using the key obtained via `get_capability_secret()`.
   - *Logic*: The canonical representation fixes subsecond floating point precision to 6 decimal places (`:.6f}`), ensuring determinism across serialization/deserialization into dict or JSON formats across all platforms.
3. **Constant-Time Verification & Fail-Closed Errors**:
   - *Observation 1.B.1 & 1.B.2*: `verify_token_signature` enforces `hmac.compare_digest` to prevent timing attacks. Missing or whitespace-only signatures raise `InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")`. Non-matching signatures raise `InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")`.
   - *Logic*: Inheriting `InvalidTokenSignatureError` from `PermissionError` preserves compatibility with existing callers like `ProcessIsolationEnvironment` (`os_sandbox.py`), while giving security auditors an exact error class for audit provenance.
4. **Strict Rejection of Legacy Tokens (Anti-Placebo)**:
   - *Observation 1.B.3 & 1.C*: Legacy tokens without a signature parse with `signature=""`. When passed to `validate()`, they are strictly rejected fail-closed, ensuring zero silent acceptance.
5. **Full Regression Integrity**:
   - *Observation 1.D*: Full repository test suite ran 497 tests with 100% pass (0 failures). `t00_meta_audit.py` verified 0 new regressions against `origin/main`.

---

## 3. Caveats

- **Scope Boundary**: Worker M3 modified only `scp/core/capability_token.py`, `scp/security/capability_epoch.py`, and created `tests/T03_capability/test_capability_token_hmac_signing.py`.
- **Sandbox Test Compatibility**: Existing tests in `tests/T03_capability/test_os_sandbox.py` already passed without modification because valid calls used `authority.issue()` and negative calls caught `PermissionError` (which is a superclass of `InvalidTokenSignatureError`). Strictness was preserved without loosening assertions (FA-01).

---

## 4. Conclusion

Milestone 3 (GAP-08) is fully implemented, verified, and complete:
1. `InvalidTokenSignatureError(PermissionError)` is defined and strictly raised on unsigned, tampered, or wrong-secret tokens.
2. Deterministic HMAC-SHA256 signature generation (`compute_token_signature`) and constant-time verification (`verify_token_signature`) are implemented in `scp/core/capability_token.py`.
3. `CapabilityToken` dataclass in `scp/security/capability_epoch.py` incorporates `signature: str = ""` and preserves it across `to_dict()` and `parse_capability_token()`.
4. `CapabilityAuthority.issue()` cryptographically signs tokens with HMAC-SHA256.
5. `CapabilityAuthority.validate()` strictly verifies HMAC-SHA256 signatures before checking epoch or subject.
6. Anti-Placebo RED probe confirmed the pre-fix vulnerability; GREEN probe confirmed post-fix fail-closed rejection.
7. 20 new comprehensive tests pass in `tests/T03_capability/test_capability_token_hmac_signing.py`.
8. All 85 capability tests pass; all 497 tests across the entire repo pass; and `t00_meta_audit.py` reports 0 new regressions.

---

## 5. Verification Method

To independently verify this milestone:

1. **Run Anti-Placebo GREEN Verification**:
   ```pwsh
   python -c @"
   import tempfile, time, os
   os.environ['SCP_CAPABILITY_SECRET'] = 'test-secret-32-chars-long-abcdef012345'
   from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken, InvalidTokenSignatureError

   with tempfile.TemporaryDirectory() as tmp:
       auth = CapabilityAuthority(state_path=os.path.join(tmp, 'caps.json'))
       forged = CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='attacker-forged', issued_at=time.time())
       try:
           auth.validate(forged, required_subject='hands:pc.write_file')
           raise AssertionError('FAILED: Forged token was accepted!')
       except InvalidTokenSignatureError:
           pass
       legit = auth.issue('hands:pc.write_file')
       assert auth.validate(legit, required_subject='hands:pc.write_file') is True
       print('PASS: Anti-Placebo GREEN verified!')
   "@
   ```
   *Expected*: `PASS: Anti-Placebo GREEN verified!` (Exit code 0)

2. **Run New Unit Tests**:
   ```pwsh
   pytest tests/T03_capability/test_capability_token_hmac_signing.py -v
   ```
   *Expected*: `20 passed` (Exit code 0)

3. **Run All Capability Tests**:
   ```pwsh
   pytest tests/T03_capability/ -v
   ```
   *Expected*: `85 passed` (Exit code 0)

4. **Run Full Test Suite**:
   ```pwsh
   pytest tests/ -q
   ```
   *Expected*: `497 passed` (Exit code 0)

5. **Run Pre-Commit Meta-Audit**:
   ```pwsh
   python tools/t00_meta_audit.py
   ```
   *Expected*: `All integrity checks passed (0 new regressions).` (Exit code 0)

6. **Invalidation Conditions**:
   - `CapabilityAuthority.validate()` accepting any unsigned or forged `CapabilityToken` without raising `InvalidTokenSignatureError`.
   - Modifying a token's subject, epoch, token_id, or issued_at while keeping the original signature and having `validate()` accept it.
   - Any regression in `pytest tests/` or `tools/t00_meta_audit.py`.
