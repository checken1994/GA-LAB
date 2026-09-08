## 2026-09-08T12:36:26Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Identity: You are Worker M3 (teamwork_preview_worker).
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_m3_r6
Original user request file: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Scope document: c:\Users\check\Downloads\scp\.agents\orchestrator_1\SCOPE.md
Explorer R6 analysis: c:\Users\check\Downloads\scp\.agents\explorer_r6\analysis.md
Explorer R6 handoff: c:\Users\check\Downloads\scp\.agents\explorer_r6\handoff.md

FILE WRITE OWNERSHIP: You exclusively own:
- c:\Users\check\Downloads\scp\scp\autofix\shadow_snapshot.py (new module)
- c:\Users\check\Downloads\scp\scp\autofix\engine_parts\autofix_mixin.py
- c:\Users\check\Downloads\scp\scp\autofix\engine_parts\verify_mixin.py
- c:\Users\check\Downloads\scp\scp\autofix\engine.py
- c:\Users\check\Downloads\scp\tests\T07_learning\test_autofix_shadow_rollback.py (new test module)
Do NOT touch any other files outside this boundary.

Mission: Implement R6: AutoFix Rollback Remediation (Cognitive Loop Perfect Isolation).
Key implementation tasks:
1. Create `scp/autofix/shadow_snapshot.py`:
   - Implement `ShadowSnapshotManager(shadow_dir: Path | str = "data/shadow")`:
     - `begin(target_files: list[Path | str], bug_id: str = "") -> str`: commits pre-patch file snapshots with SHA256 hashes and metadata manifest into `data/shadow/active/<tx_id>/`. Returns `tx_id`.
     - `rollback(tx_id: str, reason: str = "") -> bool`: atomically restores files from `data/shadow/active/<tx_id>/` via temp file + `os.replace`. Moves tx directory to `data/shadow/rolled_back/<tx_id>/`.
     - `commit(tx_id: str) -> bool`: moves `data/shadow/active/<tx_id>/` to `data/shadow/completed/<tx_id>/`.
     - `recover_abandoned_transactions() -> list[str]`: scans `data/shadow/active/` and rolls back any leftover transactions from prior process crashes.
2. In `scp/autofix/engine_parts/autofix_mixin.py`:
   - Replace volatile in-memory string backups (`ctx.pre_fix_content`) and ad-hoc `.tier3bak` with `ShadowSnapshotManager`.
   - Wrap patch application in a snapshot transaction: `begin()` before modifying files, `commit()` when verification passes, `rollback()` if verification fails or exception occurs.
3. In `scp/autofix/engine_parts/verify_mixin.py`:
   - Enforce fail-closed Reality Test (pytest) gate. If pytest fails or raises an error, do NOT fail open! Return failure and trigger rollback.
4. In `scp/autofix/engine.py`:
   - In `_auto_approve_tier3`, ensure that if `_reality_test_result` is not `PASS` (e.g. `SyntaxError`), execute immediate rollback and fail closed.
   - Run `recover_abandoned_transactions()` during AutoFix engine initialization.
5. In `tests/T07_learning/test_autofix_shadow_rollback.py`:
   - Write comprehensive unit & regression tests:
     - Test pre-patch snapshot creation under `data/shadow/`.
     - Test automatic rollback when patch introduces a syntax error or failing test.
     - Test crash recovery (`recover_abandoned_transactions()` restores modified file after simulated crash).
     - Test clean workspace: zero `.tier3bak` files in source tree.
6. Run tests via `run_command`:
   - Run `python -m pytest tests/T07_learning/test_autofix_shadow_rollback.py -v`
   - Run existing learning tests: `python -m pytest tests/T07_learning/ -q`
7. Prepare Coverage Matrix per FA-13 and verify all causal branches.
8. Write complete handoff report to `c:\Users\check\Downloads\scp\.agents\worker_m3_r6\handoff.md` and send message to parent.

## 2026-09-08T12:39:42Z
**Context**: Server restart recovery for Worker M3 (R6 Remediation).
**Content**: The host server has restarted. Please resume your implementation immediately from where you stopped.
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables. DO NOT CHEAT.
Tasks:
1. Implement `ShadowSnapshotManager` in `scp/autofix/shadow_snapshot.py` (`data/shadow/active/<tx_id>/`, atomic rollback, startup recovery).
2. Refactor `scp/autofix/engine_parts/autofix_mixin.py` to use `ShadowSnapshotManager`; eliminate RAM backups and `.tier3bak`.
3. Enforce fail-closed pytest gate in `scp/autofix/engine_parts/verify_mixin.py`.
4. Update `scp/autofix/engine.py` for reality test rollback and startup recovery.
5. Write tests in `tests/T07_learning/test_autofix_shadow_rollback.py` and run them via run_command.
6. Create Coverage Matrix (FA-13) and write handoff to `.agents/worker_m3_r6/handoff.md`.
**Action**: Resume execution, run tests, and report back when complete.
