# BRIEFING — 2026-09-07T12:50:00Z

## Mission
Execute Milestone 3 (GAP-08): Implement CapabilityToken HMAC-SHA256 signing in issue(), verification in validate(), InvalidTokenSignatureError fail-closed handling, anti-placebo RED/GREEN probe, unit tests, and full regression pass.

## 🔒 My Identity
- Archetype: teamwork_preview_worker
- Roles: implementer, qa, specialist
- Working directory: c:\Users\check\Downloads\scp\.agents\worker_m3
- Original parent: 570b10ff-8aa5-485c-9586-19db62136cd2
- Milestone: M3 (GAP-08 Capability Token HMAC-SHA256 Signing & Validation)

## 🔒 Key Constraints
- Zero-Trust and Fail-Closed principles.
- Mandatory adherence to FA-01 through FA-10.
- No self-granting authority or simulated PASS results.
- Enforce boundaries at Database/Hardware level, not via RAM/Variables.
- Exclusive Write Ownership:
  * scp/core/capability_token.py
  * scp/security/capability_epoch.py
  * tests/T03_capability/test_capability_token_hmac_signing.py
  * tests/T03_capability/test_os_sandbox.py (only if updating to use genuine issued tokens while preserving strictness)
  * .agents/worker_m3/*

## Current Parent
- Conversation ID: 570b10ff-8aa5-485c-9586-19db62136cd2
- Updated: 2026-09-07T12:50:00Z

## Task Summary
- **What to build**:
  1. Define `InvalidTokenSignatureError(PermissionError)` in `scp/core/capability_token.py`.
  2. Implement canonical HMAC-SHA256 `compute_token_signature` and constant-time `verify_token_signature`.
  3. Add `signature: str = ""` to `CapabilityToken` dataclass in `scp/security/capability_epoch.py`.
  4. Update `to_dict()` and `parse_capability_token()` to serialize/deserialize `signature`.
  5. In `CapabilityAuthority.issue(subject)`, sign with `self.secret = get_capability_secret()`.
  6. In `CapabilityAuthority.validate(token, required_subject)`, strictly verify HMAC-SHA256 signature, fail-closed on missing/tampered signature.
  7. Anti-placebo RED probe demonstrating unsigned token acceptance prior to fix.
  8. Comprehensive unit test suite in `tests/T03_capability/test_capability_token_hmac_signing.py`.
  9. Anti-placebo GREEN probe.
  10. Full regression: pytest >= 477 tests PASS (497 passed), `python tools/t00_meta_audit.py` PASS (0 regressions).
- **Success criteria**:
  - Unsigned/forged/tampered tokens raise `InvalidTokenSignatureError`.
  - Legitimate issued tokens validate cleanly.
  - All test suites pass (497/497 PASS).
  - Handoff report delivered to `.agents/worker_m3/handoff.md`.
- **Interface contracts**: PROJECT.md § Interface Contracts
- **Code layout**: PROJECT.md § Code Layout

## Key Decisions Made
- `InvalidTokenSignatureError` inherits from `PermissionError` so callers expecting `PermissionError` (e.g. sandbox) remain compatible while gaining explicit error classification.
- Canonical payload format: `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}".encode("utf-8")` ensuring deterministic string formatting across platforms and architectures.
- `verify_token_signature` raises `InvalidTokenSignatureError("Capability token is unsigned (GAP-08/FA-04)")` on empty/missing signature, and `InvalidTokenSignatureError("Capability token signature verification failed (tampered token)")` on mismatch.
- `CapabilityToken` re-exported in `scp/core/capability_token.py` via PEP 562 `__getattr__` and `__all__`, preventing circular dependency while supporting unified imports.

## Change Tracker
- **Files modified**:
  * `scp/core/capability_token.py`: Defined `InvalidTokenSignatureError`, `compute_token_signature`, `verify_token_signature`, PEP 562 `__getattr__` and `__all__`.
  * `scp/security/capability_epoch.py`: Added `signature: str = ""` to `CapabilityToken`, updated `to_dict()` and `parse_capability_token()`, updated `CapabilityAuthority.__init__` with secret param/fallback, updated `issue()` with HMAC signing, and updated `validate()` with strict verification.
  * `tests/T03_capability/test_capability_token_hmac_signing.py`: Added 20 comprehensive unit tests covering roundtrip, unsigned, tampered, wrong secret, and legacy rejection.
- **Build status**: PASS (497/497 tests PASS, exit code 0; meta-audit 0 regressions)
- **Pending issues**: None

## Quality Status
- **Build/test result**: 497 passed in 112.00s (exit 0)
- **Lint status**: Clean
- **Tests added/modified**: 20 new tests added in `tests/T03_capability/test_capability_token_hmac_signing.py`

## Loaded Skills
- **Source**: c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md
  - **Local copy**: c:\Users\check\Downloads\scp\.agents\worker_m3\skills\scp-capability-security-review\SKILL.md
  - **Core methodology**: Enforce least privilege, task/attempt scoping, fail-closed PEP before execution, deny-by-default, and audit verification.
- **Source**: c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
  - **Local copy**: c:\Users\check\Downloads\scp\.agents\worker_m3\skills\scp-dna\SKILL.md
  - **Core methodology**: 29 principles, Reality > Model, PASS != TRUE, Anti-Placebo probes, fail-closed invariants, no manufactured PASS.

## Artifact Index
- .agents/worker_m3/BRIEFING.md — Situational awareness working memory
- .agents/worker_m3/progress.md — Liveness heartbeat and milestone tracking
- .agents/worker_m3/handoff.md — 5-component handoff report
