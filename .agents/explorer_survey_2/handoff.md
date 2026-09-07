# Handoff Report — Explorer 2: GAP-08 & GAP-09 Survey

- **Auditor/Agent**: Explorer 2 (`explorer_survey_2`)
- **Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_survey_2\`
- **Task**: Investigation and blueprint survey for GAP-08 (CapabilityToken HMAC Signing) and GAP-09 (Eliminating Hardcoded Fallback Secret & Enforcing Fail-Closed Secret Configuration).
- **Date**: 2026-09-07
- **Target Git HEAD**: `bc424a4b45fdf76e0f51fbba62d7bd52dde55e5e`
- **Integrity Baseline**: `python tools/t00_meta_audit.py` PASS (0 new regressions). Current test baseline: 483 tests collected.

---

## 1. Observation

1. **GAP-08 Observation (Missing Cryptographic Signature on Dataclass Tokens)**:
   - File: `scp/security/capability_epoch.py` lines 18–32:
     ```python
     @dataclass(frozen=True)
     class CapabilityToken:
         subject: str
         epoch: int
         token_id: str
         issued_at: float

         def to_dict(self) -> dict[str, Any]:
             return {
                 "subject": self.subject,
                 "epoch": self.epoch,
                 "token_id": self.token_id,
                 "issued_at": self.issued_at,
             }
     ```
   - File: `scp/security/capability_epoch.py` lines 158–169 (`CapabilityAuthority.validate`):
     ```python
     def validate(self, token: CapabilityToken | None, required_subject: str | None = None) -> bool:
         if token is None:
             return False
         if not (hasattr(token, "subject") and hasattr(token, "epoch")):
             return False
         if required_subject is not None:
             if str(getattr(token, "subject", "")) != str(required_subject):
                 return False
         with self._lock:
             state = self._load()
             return not state["revoked"] and getattr(token, "epoch", -1) == state["epoch"]
     ```
   - File: `tests/T03_capability/test_os_sandbox.py` line 26 proves anyone can construct a token:
     `forged = CapabilityToken(subject="intruder", epoch=999, token_id="fake", issued_at=0.0)`
   - Live execution of `.agents/explorer_survey_2/probe_gap08_gap09.py` outputs verbatim:
     ```
     Attacker forged token: CapabilityToken(subject='hands:pc.write_file', epoch=0, token_id='unauthorized_attacker_id_999', issued_at=1788782810.693538)
     cap_auth.validate(forged_token) result: True
     >>> [VULNERABILITY CONFIRMED - RED]: CapabilityAuthority accepted an unsigned, forged token!
     ```

2. **GAP-09 Observation (Hardcoded Fallback Secret)**:
   - File: `scp/core/capability_token.py` lines 11–17 verbatim:
     ```python
     _SECRET_STR = os.environ.get("SCP_CAPABILITY_SECRET")
     _SECRET = _SECRET_STR.encode() if _SECRET_STR else b""

     if not _SECRET:
         logger.warning("SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.")
         _SECRET = b"dev-secret-do-not-use-in-prod-12345"
     ```
   - Live terminal execution `python -c "import os; print(os.environ.get('SCP_CAPABILITY_SECRET'))"` returns `None`.
   - Live execution of `.agents/explorer_survey_2/probe_gap08_gap09.py` outputs verbatim:
     ```
     Loaded secret when SCP_CAPABILITY_SECRET is unset: b'dev-secret-do-not-use-in-prod-12345'
     >>> [VULNERABILITY CONFIRMED - RED]: scp.core.capability_token used hardcoded dev-secret fallback!
     ```

3. **Subsystem Duality & Cross-Module Dependency Observation**:
   - `scp/core/capability_token.py` contains string-based tokens (`mint_token` / `verify_token`), and is tested by `tests/T03_capability/test_capability_token_mutation_contract.py` (all 7 tests pass).
   - `scp/hands/planner.py` sits at the intersection: lines 2–3 import both `from scp.core.capability_token import verify_token` and `from scp.security.capability_epoch import parse_capability_token`.
   - `scp/api_server.py` line 579 imports `from scp.api.routes.hands_routes import router as hands_router`, which imports `HandsPlanner`, which imports `capability_token`.
   - `tests/conftest.py` does NOT exist at the root of `tests/`.

---

## 2. Logic Chain

1. **Logic for GAP-08 (Signature Vulnerability -> Fix)**:
   - *Premise 1*: `CapabilityAuthority.validate()` accepts any token object that has `subject` matching the required action and `epoch` matching current state (`scp/security/capability_epoch.py:164-168`).
   - *Premise 2*: The epoch is publicly queryable via `status()` (or defaults to 0), and `subject` is standard (e.g. `hands:pc.write_file`).
   - *Deduction*: Therefore, any unauthorized party or internal worker can forge a valid capability token out of thin air without needing private credentials or authority permission (confirmed by probe).
   - *Remediation Logic*: To enforce Zero-Trust and FA-05, the issuing authority MUST compute an HMAC-SHA256 signature using a secret known only to the authority, attach this signature to `CapabilityToken.signature`, and `validate()` MUST recompute and verify this signature in constant time (`hmac.compare_digest`). If unsigned or invalid, it MUST fail closed by raising `InvalidTokenSignatureError(PermissionError)`.

2. **Logic for GAP-09 (Secret Vulnerability -> Fix)**:
   - *Premise 1*: If `SCP_CAPABILITY_SECRET` is unset, `scp/core/capability_token.py:16` sets `_SECRET = b"dev-secret-do-not-use-in-prod-12345"`.
   - *Premise 2*: Because this secret is published in version control, any attacker knowing this secret can forge valid signed tokens if the server runs without setting `SCP_CAPABILITY_SECRET`.
   - *Deduction*: This violates the Fail-Closed principle (DNA #2). The system must fail to start or import if the secret is missing.
   - *Test Suite Dependency Logic*: Because `scp.core.capability_token` is imported transitively during pytest test discovery/collection by `test_api_import_order_contract.py`, `test_god_split_semantic_parity.py`, etc., raising `MissingSecretError` at module import time would abort `pytest` collection unless `SCP_CAPABILITY_SECRET` is set in the test runner.
   - *Remediation Logic*: Creating a root `tests/conftest.py` with `os.environ.setdefault("SCP_CAPABILITY_SECRET", "test-capability-secret-for-automated-suites-only-32bytes")` guarantees that pytest discovery succeeds cleanly across all 483 tests while keeping production fail-closed.

---

## 3. Caveats

1. **Subsystem Duality**: There are currently two token formats in SCP: the string-based format (`mint_token`/`verify_token`) in `scp/core/capability_token.py` and the dataclass format (`CapabilityToken`) in `scp/security/capability_epoch.py`. The proposed fix maintains both: it hardens `CapabilityToken` with HMAC signing and preserves `mint_token`/`verify_token` so existing contracts in `test_capability_token_mutation_contract.py` do not break.
2. **Error Class Inheritance**: `InvalidTokenSignatureError` inherits from `PermissionError` rather than generic `Exception`. This is a deliberate, verified design decision so existing tests like `tests/T03_capability/test_os_sandbox.py` (which expects `pytest.raises(PermissionError)`) continue to pass without loosening assertions (FA-01 compliance).
3. **Multi-process / Distributed Consideration**: Because HMAC-SHA256 relies on a symmetric shared secret, all services verifying tokens in a multi-process environment must share the same `SCP_CAPABILITY_SECRET`. This is documented in `.env.example`.

---

## 4. Conclusion

1. **GAP-08 Assessment**: The vulnerability is confirmed. `CapabilityToken` in `scp/security/capability_epoch.py` is an unsigned dataclass, allowing arbitrary token forgery. The fix requires adding `signature: str`, canonical string serialization, constant-time HMAC-SHA256 verification in `CapabilityAuthority.validate()`, and raising `InvalidTokenSignatureError` on failure.
2. **GAP-09 Assessment**: The vulnerability is confirmed. `scp/core/capability_token.py` contains hardcoded `b"dev-secret-do-not-use-in-prod-12345"`. The fix requires removing this fallback, raising `MissingSecretError` when unset, creating `.env.example`, and creating `tests/conftest.py` to safeguard test collection.
3. **No Code Mutations Made**: In strict adherence to read-only exploration instructions, no source files were mutated. All findings, traces, blueprints, and adversarial probe scripts are stored in `.agents/explorer_survey_2/`.

---

## 5. Verification Method

To independently verify the survey findings:

1. **Verify Baseline Test Suite Integrity**:
   ```pwsh
   pytest tests/T03_capability/test_capability_token_mutation_contract.py -v
   python tools/t00_meta_audit.py
   ```
   *Expected*: All 7 capability contract tests pass; meta-audit reports 0 new regressions.

2. **Verify Vulnerability Reproduction (FA-09 Exploit Mandate)**:
   ```pwsh
   python .agents/explorer_survey_2/probe_gap08_gap09.py
   ```
   *Expected*: Verbatim output showing `[VULNERABILITY CONFIRMED - RED]` for both GAP-08 (forged token accepted by `CapabilityAuthority.validate()`) and GAP-09 (hardcoded fallback secret loaded when env var unset).

3. **Verify Post-Remediation Invalidation Conditions**:
   When the implementer applies the blueprint:
   - `python .agents/explorer_survey_2/probe_gap08_gap09.py` must no longer report `VULNERABILITY CONFIRMED - RED`.
   - `pytest tests/ -q` must run >= 450 tests with 100% PASS and exit code 0.
   - `python tools/t00_meta_audit.py` must pass with exit code 0.
