# Expert Panel B — Kernel P1 Durability Fixes (progress log)

- **Agent:** KERNEL DURABILITY EXPERT (panel B)
- **Repo:** C:\Users\check\Downloads\scp
- **Phase 0 snapshot:** HEAD `1d9724abec8cd36ef0df7d49e8868eb345933b86`, branch `fix/t09-golden-task-debt` (= `main` + 1 existing commit `1d9724a fix(t09): resolve baseline debt FA-04 and T09 tests`; `main` is an ancestor, `HEAD..main` empty).
  - Branch note: staying on this branch because T09 golden tests green on it depend on that existing commit; switching to bare `main` would revert T09 debt fixes out from under the required green run. No push; commit is local.
  - Pre-existing untracked file `tests/T05_gateway/conftest.py` left untouched (not in scope).
- **Skills loaded:** `scp-dna`, `scp-task-kernel-review`.

## Defect confirmation (evidence before edit)

1. **Bridge replay dedupe dead — CONFIRMED.**
   `scp/kernel_storage.py:160-164` translates `sqlite3.IntegrityError` -> `StorageIntegrityError` (a `RuntimeError`) inside `execute()`. `TaskKernel.create_task` inserts via `self.conn.execute` (`scp/task_kernel_parts/taskkernel.py:106`), so a duplicate create raises `StorageIntegrityError`. `scp/hands/task_kernel_bridge.py:339` catches only `sqlite3.IntegrityError` -> dead branch; duplicates fall to the generic "failed before dispatch" handler (`:521`, `:583`). The `"replayed": True` response can never fire.
2. **auto_reconcile_orphans unfenced — CONFIRMED.**
   `scp/task_kernel_parts/taskkernel.py:547-566`: raw `UPDATE tasks SET state='UNKNOWN'` (no version increment, no ALLOWED_TRANSITIONS check — `LEASED->UNKNOWN`/`RUNNING->UNKNOWN` are illegal per the map), staleness keyed on `tasks.updated_at` while heartbeat refreshes `leases.heartbeat_at/expires_at` (`:260`). A live worker with a valid lease but no recent state change is hijacked to UNKNOWN/RECONCILING.
3. **Checkpoint events poison the projection — CONFIRMED.**
   `taskkernel.py:312` appends `CHECKPOINT_WRITTEN` with `to_state=<checkpoint.state>` without transitioning the tasks table. `rebuild_projection` (`:689-693`) takes the last non-null `to_state`, so a crash after checkpoint projects the snapshot state (e.g. WAITING_TOOL) as the task state — a state never legally reached by STATE_TRANSITION.
4. **No heartbeat across awaited dispatch — CONFIRMED (bonus).**
   Bridge claims ttl 60s (`task_kernel_bridge.py:369`) then awaits `executor.execute` (`:427`) with no heartbeat; actions >60s lose the lease mid-flight, and even the UNKNOWN persistence path (`record_action_dispatched` -> `_assert_lease`) fails afterwards.

## Dependency checks (no test depends on broken behavior)

- `auto_reconcile_orphans`: only production caller `scp/api/background_jobs.py:226` (watchdog tick, no tests).
- `CHECKPOINT_WRITTEN`: referenced only in `taskkernel.py:312`; no test reads its `to_state`.
- `tests/T04_kernel/test_kernel_crash_consistency.py` — rebuild tests use STATE_TRANSITION-only journals; unaffected.
- `tests/T10_recovery/test_adversarial_chaos_matrix.py` — kill-after-checkpoint asserts `to in {"RECOVERING","HUMAN_REVIEW"}`; after fix it recovers to HUMAN_REVIEW (RUNNING mapping in `recover_on_boot`), still inside the asserted contract.
- `scp/ask_kernel_adapter.py:171` checkpoints with state RUNNING while the table is RUNNING; with `to_state=None` rebuild still yields RUNNING. Unaffected.
- Golden T09 replay assertions (`success is False`, `safeToRetry is False`, target unmodified) hold under the repaired replay path.
- SQLite parses `now_iso()` (`2026-...+00:00`) via `strftime('%s', ...)` — verified empirically; staleness SQL pre-filter kept, CAST added.

## Fixes applied (files)

- `scp/hands/task_kernel_bridge.py`
  - Catch `(StorageIntegrityError, sqlite3.IntegrityError)` on duplicate `create_task` so the replayed-response branch actually fires (defect 1).
  - Heartbeat the lease in a background asyncio task around the awaited dispatch; ttl hoisted to `self.lease_ttl_seconds` (default 60.0, behavior unchanged) (defect 4).
- `scp/task_kernel_parts/taskkernel.py`
  - `auto_reconcile_orphans`: lease-authority gate (skip when an unreleased lease with `expires_at > now` exists), staleness cutoff bound as parameter, state changes only through `ALLOWED_TRANSITIONS` (LEASED/RUNNING -> RECOVERING -> RECONCILING) with `version=version+1`, event payload records lease heartbeat/expires evidence, sweep releases the dead lease + decrements queue account (defect 2).
  - `checkpoint()`: append `CHECKPOINT_WRITTEN` with `to_state=None` (from_state already None) so the projection never derives a checkpoint snapshot state; checkpoint state remains authoritative in `checkpoints.state` (defect 3).
- `tests/T04_kernel/test_kernel_p1_regressions.py` (new): regression tests (a)-(d).

## Test evidence

- Negative control (fixes stashed, tests kept): `tests/T04_kernel/test_kernel_p1_regressions.py` ->
  `3 failed, 2 passed` — (a) replay, (b) orphan sweep, (c) checkpoint projection FAIL pre-fix
  (`assert 'WAITING_TOOL' is None` on the poisoned projection); after strengthening (d) with a
  heartbeat spy, (d) also fails pre-fix (`len([]) == 0`, no lease renewal) — all four tests are load-bearing.
- `python -m pytest tests/T04_kernel/ tests/T09_golden_task/test_golden_a_agent_os.py -q --no-header`
  -> `23 passed in 4.00s` (includes 5 new regression tests).
- `python -m pytest tests/T00_integrity -q --no-header` -> `54 passed in 8.35s`.
- Extra (touched paths): `python -m pytest tests/T10_recovery/test_adversarial_chaos_matrix.py -q --no-header`
  -> `2 passed in 0.80s` (real hard-kill after checkpoint still recovers; now maps to HUMAN_REVIEW,
  inside the test's asserted contract `{"RECOVERING","HUMAN_REVIEW"}`).
- Commit: `fixB(kernel)` on branch `fix/t09-golden-task-debt`, parent `1d9724abec8cd36ef0df7d49e8868eb345933b86`, files: `scp/hands/task_kernel_bridge.py`, `scp/task_kernel_parts/taskkernel.py`, `tests/T04_kernel/test_kernel_p1_regressions.py`, this log. Not pushed.

## Verdict per mission item

- (a) replayed response: VERIFIED (fails pre-fix, passes post-fix; golden T09 replay still green).
- (b) orphan sweep fencing: VERIFIED (fails pre-fix, passes post-fix).
- (c) checkpoint projection: VERIFIED (fails pre-fix, passes post-fix; no existing test depended on checkpoint to_state).
- (d) heartbeat across dispatch: VERIFIED at unit scope (fails pre-fix via heartbeat spy, passes post-fix with ttl=1s and 2.4s dispatch). Limits: production dispatch durations/TTLs not exercised here; single-node SQLite only.

## Open questions / limits

- Single-node SQLite durability only; no HA claim.
- The orphan sweep and `expire_leases` overlap by design; both are legal recovery paths and the transition map keeps them composable.
