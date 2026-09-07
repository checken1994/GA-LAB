# BRIEFING — 2026-09-07T12:07:35Z

## Mission
Survey and architectural blueprint for GAP-08 (CapabilityToken HMAC Signing) and GAP-09 (Eliminating Hardcoded Fallback Secret & Enforcing Fail-Closed Secret Configuration).

## 🔒 My Identity
- Archetype: explorer
- Roles: survey, investigation, synthesis
- Working directory: c:\Users\check\Downloads\scp\.agents\explorer_survey_2\
- Original parent: 50f4125f-5432-4084-856a-8d91aba6378c
- Milestone: GAP-08 and GAP-09 survey complete

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source code files
- Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-10
- Write only to .agents/explorer_survey_2/
- Work in Vietnamese with English technical identifiers

## Current Parent
- Conversation ID: 50f4125f-5432-4084-856a-8d91aba6378c
- Updated: 2026-09-07T12:07:35Z

## Investigation State
- **Explored paths**:
  - `scp/core/capability_token.py`
  - `scp/security/capability_epoch.py`
  - `scp/hands/hands_executor.py`
  - `scp/hands/task_kernel_bridge.py`
  - `scp/hands/planner.py`
  - `scp/security/os_sandbox.py`
  - `scp/api/routes/hands_routes.py`
  - `tests/T03_capability/test_capability_token_mutation_contract.py`
  - `tests/T03_capability/test_hands_authority_pep.py`
  - `tests/T03_capability/test_os_sandbox.py`
  - `tools/t00_meta_audit.py`
  - `deploy/vps/scp.env.example`
- **Key findings**:
  - Confirmed GAP-08 vulnerability via live exploit script (`probe_gap08_gap09.py`): unsigned forged `CapabilityToken` is accepted by `CapabilityAuthority.validate()`.
  - Confirmed GAP-09 vulnerability via live exploit script: unset `SCP_CAPABILITY_SECRET` defaults to `b"dev-secret-do-not-use-in-prod-12345"`.
  - Detailed the full token Call Graph and Execution Trace across the PEP and planner boundaries.
  - Specified HMAC-SHA256 canonical signing algorithm, constant-time verification, and `InvalidTokenSignatureError(PermissionError)` fail-closed error class.
  - Formulated the test fixture strategy (`tests/conftest.py`) to prevent pytest test collection crashes when `MissingSecretError` is enforced at module import time.
- **Unexplored areas**: None within the scope of GAP-08 and GAP-09.

## Key Decisions Made
- `InvalidTokenSignatureError` inherits from `PermissionError` to maintain compatibility with existing tests like `test_os_sandbox.py` without loosening assertions.
- Root `tests/conftest.py` is recommended to supply a deterministic `SCP_CAPABILITY_SECRET` during test collection.
- `mint_token` and `verify_token` in `scp/core/capability_token.py` are preserved to satisfy `test_capability_token_mutation_contract.py`.

## Artifact Index
- DISPATCH.md — Incoming task instructions
- BRIEFING.md — Persistent working memory and state
- progress.md — Liveness heartbeat
- probe_gap08_gap09.py — Standalone adversarial probe validating RED state (FA-09)
- analysis.md — Full deep-dive analysis report
- handoff.md — 5-component handoff report
