# Worker M2 Dispatch: Milestone 1 Verification & Milestone 2 (GAP-09) Implementation

- Working Directory: c:\Users\check\Downloads\scp\.agents\worker_m2
- Authoritative User Request: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
- Project Scope: c:\Users\check\Downloads\scp\.agents\orchestrator_7\PROJECT.md
- Survey Reference: c:\Users\check\Downloads\scp\.agents\explorer_survey_2\analysis.md
- Milestone 1 Reference: c:\Users\check\Downloads\scp\.agents\worker_m1\handoff.md

## Exclusive Write Ownership
- `scp/core/capability_token.py`
- `.env.example`
- `deploy/vps/scp.env.example`
- `tests/conftest.py`
- `tests/T03_capability/test_capability_secret_fail_closed.py`
- `.agents/worker_m2/*`

## Tasks
1. Verify Milestone 1 status:
   - Run `git grep "RLock" scp/kernel_storage.py` and `python tools/probe_gap05_occ_multiprocess.py`.
   - Run `pytest tests/T04_kernel/test_kernel_storage.py -v`.
   - Record exact terminal outputs in handoff.md.
2. Execute Milestone 2 (GAP-09):
   - Run RED probe on GAP-09 (confirm fallback secret active when unset).
   - Create `tests/conftest.py` to set `os.environ.setdefault("SCP_CAPABILITY_SECRET", "test-capability-secret-for-automated-suites-only-32bytes")` to prevent test collection crashes.
   - Create `.env.example` at repo root documenting `SCP_CAPABILITY_SECRET`.
   - Update `deploy/vps/scp.env.example` with `SCP_CAPABILITY_SECRET`.
   - In `scp/core/capability_token.py`:
     * Define `class MissingSecretError(RuntimeError): ...`
     * Define `get_capability_secret() -> bytes` reading `SCP_CAPABILITY_SECRET`. If unset or empty, raise `MissingSecretError`.
     * Remove `b"dev-secret-do-not-use-in-prod-12345"` fallback completely.
     * At module top-level, set `_SECRET = get_capability_secret()`.
   - Write comprehensive tests in `tests/T03_capability/test_capability_secret_fail_closed.py` verifying fail-closed behavior when `SCP_CAPABILITY_SECRET` is unset, and successful operation when set.
   - Run GREEN probe on GAP-09.
   - Run `pytest tests/T03_capability/ -v`.
   - Run `python tools/t00_meta_audit.py`.
3. Deliver handoff report to `.agents/worker_m2/handoff.md` with:
   - Observation (terminal outputs, commands, SHA).
   - Logic Chain (why changes are fail-closed and adhere to zero-trust).
   - Caveats.
   - Conclusion.
   - Verification Method.

## 2026-09-07T12:26:00Z
Received dispatch for Worker M2: Milestone 1 Verification & Milestone 2 (GAP-09) Implementation.
Verified exclusive write ownership and required steps.
