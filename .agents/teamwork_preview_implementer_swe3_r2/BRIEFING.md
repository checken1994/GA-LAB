# BRIEFING — teamwork_preview_implementer_swe3_r2

## Objective
Execute Round 2 adversarial review and refinement against GAP-11 remediation in `scp/task_kernel_parts/taskkernel.py`:
Specifically:
1. Attack the lease expiration watchdog (`expire_leases()`) racing against `commit_completed()`.
2. Verify that if a lease expires or is revoked/released, a subsequent or racing `commit_completed()` is strictly rejected with `StaleLease` (or its subclass `OptimisticLockError`, or `InvalidTransition`) and cannot force a `COMPLETED` state.
3. Test edge cases:
   - Worker attempts `commit_completed()` after lease TTL has passed, but before watchdog runs.
   - Worker attempts `commit_completed()` after watchdog `expire_leases()` has transitioned task to `HUMAN_REVIEW` (from `VERIFYING`) or `RECOVERING` (from `RUNNING`).
   - Watchdog and worker race concurrently across multi-threads: watchdog trying to expire lease while worker tries to commit completion.
   - Worker attempts `commit_completed()` after lease was explicitly released/revoked via `release()`.
   - Worker attempts `commit_completed()` with fencing token rendered stale by lease expiration followed by task re-acquisition by a new worker.
4. Verify physical SQLite DB boundary (raw inspection).
5. Ensure 100% PASS on `tests/T04_kernel/` and 0 regressions on `tools/t00_meta_audit.py`.
6. Commit and push to main.
