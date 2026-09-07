# BRIEFING — teamwork_preview_implementer_swe3_r3

## Objective
Execute Round 3 adversarial review, multi-process concurrency testing, and empirical verification for GAP-11 remediation in `scp/task_kernel_parts/taskkernel.py`:
Specifically:
1. Multi-Process Concurrency Attack:
   - Spawn multiple independent OS Python processes opening the exact same physical SQLite database file concurrently.
   - Race multi-process workers attempting `claim()`, `transition()`, `commit_completed()`, `expire_leases()`, and `release()`.
   - Verify that SQLite file locking and TaskKernel optimistic locking handle multi-process contention cleanly without database corruption, split-brain states, or unauthorized transitions to `COMPLETED`.
2. Hardware/OS Edge Cases & Durability:
   - Test transaction rollback integrity: verify that a failed `commit_completed()` (due to lease mismatch or simulated mid-transaction failure) rolls back cleanly and leaves no orphan state or partial event journal entries.
   - Verify `PRAGMA integrity_check` and journal sequence consistency after heavy multi-process hammer.
3. Verification Suite:
   - Verify all baseline probes (`probe_gap11.py`, `probe_gap11_adversarial_break_attempt.py`, `probe_gap11_r2_watchdog_race.py`).
   - Run new multi-process probe (`probe_gap11_r3_multiprocess_concurrency.py`).
   - Verify full `tests/T04_kernel/` suite PASS (100%).
   - Verify `tools/t00_meta_audit.py` PASS with 0 regressions.
4. FA-11 & FA-12 Empirical Closure + FA-13 Coverage Matrix:
   - Formally document the FA-13 Coverage Matrix with Orchestrator-approved UNPROVEN_BRANCH entries for GAP-12 and GAP-13 (anti-scope creep preserved).
5. Deliverables:
   - Add new tests in `tests/T04_kernel/test_adversarial_kernel_flaws.py`.
   - Document handoff in `handoff.md`.
   - Push to `origin/main` if tests added.
