# Handoff Report: Milestone 3 (GAP-08) Adversarial Penetration Testing

**Agent**: Challenger 1 (`teamwork_preview_challenger`)  
**Parent Agent**: `570b10ff-8aa5-485c-9586-19db62136cd2`  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\challenger_m3_1\`  
**Date**: 2026-09-07T19:55:00+07:00 (2026-09-07T12:55:00Z)  
**HEAD SHA**: `bc424a4b45fdf76e0f51fbba62d7bd52dde55e5e`  
**Verdict**: **APPROVE** (100.00% of token forgery, cryptographic mutation, and payload tampering attacks blocked fail-closed)  
**Standards**: SCP DNA (29 Principles), Zero-Trust, Fail-Closed, FA-01 through FA-10, Exploit Mandate (FA-09)

---

## 1. Observation

### A. Codebase Analysis & Attack Surface Discovery
1. **`scp/core/capability_token.py` (lines 16-38, 40-54)**:
   - `InvalidTokenSignatureError` inherits from `PermissionError`:
     ```python
     class InvalidTokenSignatureError(PermissionError):
         """Raised when a capability token is unsigned, has an invalid signature, or has been tampered with."""
         pass
     ```
   - Canonical signature computation:
     ```python
     def compute_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float) -> str:
         canonical = f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")
         return hmac.new(secret, canonical, hashlib.sha256).hexdigest()
     ```
   - Constant-time verification with fail-closed semantics:
     ```python
     def verify_token_signature(secret: bytes, subject: str, epoch: int, token_id: str, issued_at: float, signature: str) -> bool:
         if not signature or not str(signature).strip():
             raise InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")
         expected = compute_token_signature(secret, subject, epoch, token_id, issued_at)
         if not hmac.compare_digest(str(signature).strip(), expected):
             raise InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")
         return True
     ```
   - Mandatory secret loading: `get_capability_secret()` strictly raises `MissingSecretError` if `SCP_CAPABILITY_SECRET` is unset or empty.
2. **`scp/security/capability_epoch.py` (lines 25-41, 182-220)**:
   - `CapabilityToken` dataclass incorporates `signature: str = ""`.
   - `CapabilityAuthority.issue()` signs tokens with HMAC-SHA256:
     ```python
     signature = compute_token_signature(
         secret=self.secret,
         subject=subject,
         epoch=epoch,
         token_id=token_id,
         issued_at=issued_at,
     )
     ```
   - `CapabilityAuthority.validate()` enforces signature verification prior to checking subject or epoch:
     ```python
     signature = getattr(token, "signature", "")
     verify_token_signature(
         secret=self.secret,
         subject=str(token.subject),
         epoch=int(token.epoch),
         token_id=str(getattr(token, "token_id", "")),
         issued_at=float(getattr(token, "issued_at", 0.0)),
         signature=signature,
     )
     ```

### B. Empirical Adversarial Penetration Testing (FA-09 Exploit Mandate)
We authored and executed an independent penetration harness at `tools/probes/probe_challenger_m3_token_forgery.py` testing 10 adversarial attack categories:

```pwsh
python tools/probes/probe_challenger_m3_token_forgery.py
```

**Verbatim Execution Summary**:
```
================================================================================
CHALLENGER 1 ADVERSARIAL PENETRATION TEST SUITE: TOKEN FORGERY & CRYPTO ATTACKS
Target Secret: producti... (length: 41)
================================================================================
[BASELINE] Legitimate token issued and verified: PASS

--- CATEGORY 1: Out-of-Thin-Air Forgery Attacks ---
  [BLOCKED] Unsigned token dataclass: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Random 64-char hex signature: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)
  [BLOCKED] All-zero 64-char signature: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)
  [BLOCKED] All-f 64-char signature: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)
  [BLOCKED] Short random alphanumeric string: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)
  [BLOCKED] Forged via dict deserialization: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)
  [BLOCKED] Forged via JSON string deserialization: InvalidTokenSignatureError: Capability token signature verification failed (tampered token)

--- CATEGORY 2: Known/Stale Secret Forgery Attacks ---
  [BLOCKED] Signed with Old GAP-09 dev fallback secret: InvalidTokenSignatureError
  [BLOCKED] Signed with Common default 'secret': InvalidTokenSignatureError
  [BLOCKED] Signed with Common default 'password': InvalidTokenSignatureError
  [BLOCKED] Signed with Common default 'default': InvalidTokenSignatureError
  [BLOCKED] Signed with Common default 'admin': InvalidTokenSignatureError
  [BLOCKED] Signed with Common default 'changeme': InvalidTokenSignatureError
  [BLOCKED] Signed with Common numeric default: InvalidTokenSignatureError
  [BLOCKED] Signed with Predictable project-name secret: InvalidTokenSignatureError

--- CATEGORY 3: Weak and Mismatched Key Attacks ---
  [BLOCKED] Signed with Empty key (b''): InvalidTokenSignatureError
  [BLOCKED] Signed with Whitespace key: InvalidTokenSignatureError
  [BLOCKED] Signed with Null bytes 32-byte key: InvalidTokenSignatureError
  [BLOCKED] Signed with Truncated target secret (by 1 char): InvalidTokenSignatureError
  [BLOCKED] Signed with Extended target secret: InvalidTokenSignatureError
  [BLOCKED] Signed with Case-altered target secret: InvalidTokenSignatureError
  [BLOCKED] Signed with Different authority secret: InvalidTokenSignatureError

--- CATEGORY 4: Bit-Flipping & Signature Mutation Attacks ---
  [BLOCKED] Bit-flip at offset 0: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 1: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 15: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 31: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 32: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 47: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 62: InvalidTokenSignatureError
  [BLOCKED] Bit-flip at offset 63: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 63 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 60 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 48 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 32 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 16 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 8 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 4 chars: InvalidTokenSignatureError
  [BLOCKED] Signature truncated to 1 chars: InvalidTokenSignatureError
  [BLOCKED] Signature extended by 1 chars: InvalidTokenSignatureError
  [BLOCKED] Signature extended by 4 chars: InvalidTokenSignatureError
  [BLOCKED] Signature extended by 64 chars: InvalidTokenSignatureError
  [BLOCKED] Uppercase signature: InvalidTokenSignatureError
  [BLOCKED] Null byte in signature: InvalidTokenSignatureError

--- CATEGORY 5: Payload Modification & Privilege Escalation Attacks ---
  [BLOCKED] Elevate subject to hands:pc.write_file: InvalidTokenSignatureError
  [BLOCKED] Elevate subject to hands:pc.bash_exec: InvalidTokenSignatureError
  [BLOCKED] Elevate subject to root wildcard '*': InvalidTokenSignatureError
  [BLOCKED] Elevate subject to admin: InvalidTokenSignatureError
  [BLOCKED] Increment epoch by 1 (future evasion): InvalidTokenSignatureError
  [BLOCKED] Increment epoch by 100: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch to -1: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch to -100: InvalidTokenSignatureError
  [BLOCKED] Swap token_id to attacker string: InvalidTokenSignatureError
  [BLOCKED] Swap token_id to another valid uuid: InvalidTokenSignatureError
  [BLOCKED] Manipulate timestamp: add 10 seconds: InvalidTokenSignatureError
  [BLOCKED] Manipulate timestamp: subtract 10 seconds: InvalidTokenSignatureError
  [BLOCKED] Manipulate timestamp precision (+0.000001): InvalidTokenSignatureError
  [BLOCKED] Manipulate timestamp to 0.0: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to 4: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to 3: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to 2: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to 1: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to 0: InvalidTokenSignatureError
  [BLOCKED] Decrement epoch from 5 to -1: InvalidTokenSignatureError
  [BLOCKED] Canonical delimiter confusion attack: InvalidTokenSignatureError

--- CATEGORY 6: Legacy Unsigned / Absent Signature Ingestion ---
  [BLOCKED] Legacy dataclass with empty signature string: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy dataclass with whitespace signature: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy dataclass with None signature: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy dict without signature key: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy dict with signature=None: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy dict with signature='': InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy JSON str without signature key: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy JSON str with signature=null: InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)
  [BLOCKED] Legacy JSON str with signature='': InvalidTokenSignatureError: Capability token is unsigned (GAP-08/FA-04)

--- CATEGORY 7: High-Volume Adversarial Fuzzing (500 Iterations) ---
  Fuzzing completed: 500/500 attacks blocked fail-closed.

--- CATEGORY 8: Boundary Type & Signature Object Mutations ---
  [BLOCKED] Integer signature (123456789): InvalidTokenSignatureError
  [BLOCKED] Boolean False signature: InvalidTokenSignatureError
  [BLOCKED] Boolean True signature: InvalidTokenSignatureError
  [BLOCKED] Float signature (3.14159): InvalidTokenSignatureError
  [BLOCKED] Bytes signature (b'deadbeef'*8): InvalidTokenSignatureError
  [BLOCKED] Empty list signature: InvalidTokenSignatureError
  [BLOCKED] Dictionary signature: InvalidTokenSignatureError
  [BLOCKED] None object: safely rejected (returned False)
  [BLOCKED] Generic object(): safely rejected (returned False)
  [BLOCKED] Plain string: safely rejected (returned False)
  [BLOCKED] Integer: safely rejected (returned False)
  [BLOCKED] Plain dict: safely rejected (returned False)

--- CATEGORY 9: Unicode, Emojis, and Special Characters in Subject ---
  [BLOCKED] Tampered Vietnamese subject: InvalidTokenSignatureError
  [BLOCKED] Tampered Emoji subject: InvalidTokenSignatureError
  [BLOCKED] Tampered Path traversal in subject: InvalidTokenSignatureError
  [BLOCKED] Tampered Newline in subject: InvalidTokenSignatureError
  [BLOCKED] Tampered Null byte in subject: InvalidTokenSignatureError

--- CATEGORY 10: State File Tampering & Revocation Invariant ---
  [BLOCKED] Valid token rejected after revocation (returned False)
  [BLOCKED] Corrupt state file rejected fail-closed (returned False)

================================================================================
PENETRATION TEST SUMMARY
Total Adversarial Attacks Attempted: 592
Successfully Blocked Fail-Closed:   592
Bypasses / Leaks Detected:          0
Block Rate:                          100.00%
================================================================================

FINAL PENETRATION VERDICT: APPROVE (100% of attacks blocked fail-closed)
```

### C. Capability Unit Tests & Regression Verification
1. **GAP-08 Unit Tests**:
   - Command: `pytest tests/T03_capability/test_capability_token_hmac_signing.py -v`
   - Output: `20 passed in 0.73s`, exit code 0.
2. **Capability Test Suite**:
   - Command: `pytest tests/T03_capability/ --basetemp=reports/pytest-basetemp-challenger1 -v`
   - Output: `85 passed in 2.24s`, exit code 0.
3. **Full Repository Regression Suite**:
   - Command: `pytest tests/ --basetemp=reports/pytest-basetemp-challenger1 -q`
   - Output: `497 passed in 155.92s (0:02:35)`, exit code 0.
4. **Pre-Commit Meta-Audit Regression Guard**:
   - Command: `python tools/t00_meta_audit.py`
   - Output: `All integrity checks passed (0 new regressions).`, exit code 0.

---

## 2. Logic Chain

1. **Attack Vector 1 (Out-of-thin-air Forgery)**:
   - *Observation 1.B (Cat 1)*: Tokens fabricated without knowledge of the secret (random hex, all-zero, all-f, arbitrary strings, or parsed from dict/JSON) were submitted to `validate()`.
   - *Logic*: In all cases, `verify_token_signature` computes `expected = compute_token_signature(...)` using the authority's secret. Because SHA-256 is collision-resistant and the attacker has no oracle or valid secret, `hmac.compare_digest` returns `False`, raising `InvalidTokenSignatureError`.
2. **Attack Vector 2 (Old Fallback / Default Secret Forgery)**:
   - *Observation 1.B (Cat 2)*: Tokens signed with `b"dev-secret-do-not-use-in-prod-12345"` or common default keys (`b"admin"`, `b"secret"`, `b"password"`) were evaluated against an authority with production secret.
   - *Logic*: All 8 were rejected with `InvalidTokenSignatureError`, proving that the old fallback secret is completely dead and provides zero bypass capability.
3. **Attack Vector 3 (Weak / Mismatched Key Forgery)**:
   - *Observation 1.B (Cat 3)*: Tokens signed with empty keys `b""`, whitespace keys, null-byte keys, or truncated keys were tested.
   - *Logic*: HMAC-SHA256 ensures cryptographic domain separation; any difference in key bytes alters the output MAC completely, strictly triggering `InvalidTokenSignatureError`.
4. **Attack Vector 4 (Bit-Flipping & Signature Mutilation)**:
   - *Observation 1.B (Cat 4)*: Flipping single bits at offsets 0, 1, 15, 31, 32, 47, 62, 63, truncating signatures to 63, 48, 32, 16, 1 chars, extending signatures, and mutating hex casing all resulted in `InvalidTokenSignatureError`.
   - *Logic*: Constant-time comparison `hmac.compare_digest` prevents early exit timing attacks and requires exact character equality across the entire 64-hex string.
5. **Attack Vector 5 (Payload Tampering & Privilege Escalation)**:
   - *Observation 1.B (Cat 5)*: Legitimate tokens issued for `hands:pc.read` had their subject changed to `hands:pc.write_file`, `hands:pc.bash_exec`, `*`, or `admin`; epoch changed (+1, +100, -1, 4, 3, 2, 1, 0); token ID substituted; or timestamp modified (+10s, -10s, precision change).
   - *Logic*: The canonical representation binds all fields `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}"`. Any alteration to any field changes the MAC digest, rendering the signature invalid.
6. **Attack Vector 6 (Legacy Unsigned Ingestion)**:
   - *Observation 1.B (Cat 6)*: Pre-GAP-08 legacy tokens without signatures (dataclass, dict, JSON, empty, or whitespace) were submitted to `validate()`.
   - *Logic*: Lines 32-33 of `capability_token.py` check `if not signature or not str(signature).strip(): raise InvalidTokenSignatureError(...)`. Legacy tokens are strictly rejected fail-closed, ensuring no backwards-compatibility loophole exists.
7. **Attack Vector 7-10 (High-Volume Fuzzing & Edge Cases)**:
   - *Observation 1.B (Cat 7-10)*: 500 randomized fuzzing iterations, type-mismatched signatures, unicode subjects, emojis, path traversal payloads, and corrupt state files all failed closed.

---

## 3. Caveats

- **Scope Boundary**: Review and testing focused strictly on `CapabilityAuthority` and `CapabilityToken` cryptographic integrity (GAP-08 / Milestone 3).
- **Windows File Lock Artifact**: Pytest required `--basetemp=reports/pytest-basetemp-challenger1` due to concurrent or lingering SQLite file locks in the shared default basetemp directory. This is an environment concurrency characteristic, not a product vulnerability.
- No other caveats.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone 3 (GAP-08) is cryptographically robust, fail-closed, and completely resistant to token forgery:
1. 100% of adversarial penetration attacks (592/592) were blocked fail-closed.
2. Zero privilege escalation or signature bypass paths were discovered.
3. Legacy unsigned tokens and tokens signed with the retired fallback secret are strictly rejected with `InvalidTokenSignatureError`.
4. Constant-time comparison prevents timing side-channels.
5. All 20 signing unit tests pass, and all 85 capability tests pass.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

1. **Run Challenger Adversarial Penetration Harness**:
   ```pwsh
   python tools/probes/probe_challenger_m3_token_forgery.py
   ```
   *Expected*: `FINAL PENETRATION VERDICT: APPROVE (100% of attacks blocked fail-closed)`, Exit code: 0.

2. **Run GAP-08 Unit Tests**:
   ```pwsh
   pytest tests/T03_capability/test_capability_token_hmac_signing.py -v
   ```
   *Expected*: `20 passed in <1s`, Exit code: 0.

3. **Run All Capability Tests**:
   ```pwsh
   pytest tests/T03_capability/ --basetemp=reports/pytest-basetemp-challenger1 -v
   ```
   *Expected*: `85 passed`, Exit code: 0.

4. **Run Full Test Suite**:
   ```pwsh
   pytest tests/ --basetemp=reports/pytest-basetemp-challenger1 -q
   ```
   *Expected*: `497 passed`, Exit code: 0.

5. **Run Pre-Commit Meta-Audit**:
   ```pwsh
   python tools/t00_meta_audit.py
   ```
   *Expected*: `All integrity checks passed (0 new regressions).`, Exit code: 0.

6. **Invalidation Conditions**:
   - Any token forged without the secret being accepted by `CapabilityAuthority.validate()`.
   - Modifying a token's subject from `hands:pc.read` to `hands:pc.write_file` while having `validate()` accept it.
   - Any regression in the capability test suite or full test suite.
