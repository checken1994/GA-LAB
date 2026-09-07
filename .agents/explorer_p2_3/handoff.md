# Handoff Report: FA-09 Exploit Probe & Mutation Anti-Placebo Strategy for GAP-02

> **Agent**: Explorer P2-3 (`teamwork_preview_explorer`)  
> **Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_p2_3`  
> **Recipient**: Orchestrator (`orchestrator_3` / Conv ID: `4aab71c9-e6ee-472b-8c41-c64e48735a24`)  
> **Mission**: Design the FA-09 Exploit Probe script and Mutation Anti-Placebo testing strategy for GAP-02 (OCC Blind Overwrites).  
> **Status**: COMPLETED  
> **Artifacts Produced**:
> - `c:\Users\check\Downloads\scp\.agents\explorer_p2_3\analysis.md` (Comprehensive Architectural Analysis & Design)
> - `c:\Users\check\Downloads\scp\.agents\explorer_p2_3\probe_satellite_blind_overwrite.py` (FA-09 Executable Exploit Probe)
> - `c:\Users\check\Downloads\scp\.agents\explorer_p2_3\handoff.md` (This 5-Component Handoff Report)

---

## 1. Observation

1. **Storage and DAO Update Audit (`scp/task_kernel.py` & `scp/task_kernel_parts/taskkernel.py`)**:
   - `idempotency` table:
     * Line `scp/task_kernel.py:188`: `UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?`
     * Line `scp/task_kernel.py:232`: `UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?`
     * Line `scp/task_kernel.py:293`: `UPDATE idempotency SET status=?,result_ref=? WHERE logical_key=?`
     * Line `scp/task_kernel_parts/taskkernel.py:610, 614, 618, 660, 687`: All execute blind `UPDATE idempotency` without `WHERE version=?`.
     * Schema definition (`scp/task_kernel_parts/taskkernel.py:54`): `CREATE TABLE IF NOT EXISTS idempotency (logical_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, step_id TEXT NOT NULL, action_type TEXT NOT NULL, resource_identity TEXT NOT NULL, status TEXT NOT NULL, result_ref TEXT, created_at TEXT NOT NULL)` — **Completely lacks a `version` column**.
   - `leases` table:
     * Line `scp/task_kernel_parts/taskkernel.py:388` (`heartbeat`): `UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?` — **No version check, and no check for `released=0`**.
     * Lines `scp/task_kernel_parts/taskkernel.py:214, 416, 441, 723, 756, 842, 923` and `task_kernel.py:304`: Execute blind release `UPDATE leases SET released=1 WHERE lease_id=?` without checking version.
     * Schema definition (`scp/task_kernel_parts/taskkernel.py:54`): `CREATE TABLE IF NOT EXISTS leases (...)` — **Completely lacks a `version` column**.
   - `queue_accounts` table:
     * Lines `216, 418, 448, 578, 628, 724, 758, 845, 925`: `UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=?` — **Completely lacks a `version` column**.
   - `control` table:
     * Line `738`: `UPDATE control SET global_kill=?,global_kill_epoch=? WHERE id=1` — **Lacks a `version` column**.
   - `events` and `checkpoints` tables:
     * These tables are purely append-only (no `UPDATE` statements exist anywhere in the codebase).

2. **Absence of `OptimisticLockError`**:
   - Grep search across the entire repository for `OptimisticLockError` returned **0 matches**.
   - In Phase 1, `StaleLease(KernelError)` was used on `tasks` table concurrency conflicts.

3. **FA-09 Empirical Probe Execution**:
   - Standalone probe `probe_satellite_blind_overwrite.py` was executed directly via `python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py`.
   - **Terminal Output Verified**:
     * `Probe 1 (Idempotency Blind Overwrite)`: Stale Worker 2 executed `UPDATE idempotency` and clobbered Worker 1's authoritative result `evidence://worker_1_valid...` with `evidence://worker_2_STALE_OVERWRITE...`. Crash confirmed with `BlindOverwriteFlawError`.
     * `Probe 2 (Lease Heartbeat Blind Overwrite)`: A heartbeat on a released lease (`released=1`) extended `expires_at` into the future without error. Crash confirmed with `BlindOverwriteFlawError`.
     * `Probe 3 (Satellite Artifact Blind Overwrite)`: Worker B blindly overwrote Worker A's artifact update without error. Crash confirmed with `BlindOverwriteFlawError`.
     * **Result**: 3/3 vulnerabilities reproduced on live terminal with raw exception/crash output (Exit code 0 indicating exploit reproduction complete).

---

## 2. Logic Chain

1. **Premise 1 (INV-01 Violation)**: An Agent OS requires strict atomic state fencing at the database level. If a table undergoes state transitions or mutable updates, concurrent or out-of-order writes without version fencing permit lost updates and split-brain states.
2. **Premise 2 (Empirical Proof via Probe)**: Observation 3 proves that without a `version` column and without `WHERE version=?`, concurrent/interleaved updates to `idempotency`, `leases`, and satellite tables execute with `rowcount == 1` and silently obliterate earlier committed state without raising any error.
3. **Premise 3 (The Exploit Mandate FA-09)**: Because `probe_satellite_blind_overwrite.py` crashed with explicit `BlindOverwriteFlawError` on the terminal demonstrating silent data clobbering, the existence of vulnerability GAP-02 is fully proven under FA-09.
4. **Premise 4 (Post-Fix Invariant)**: In Milestone M3, every mutable satellite table must have a `version` column, and every `UPDATE` must specify `WHERE ... AND version=?`. If `cur.rowcount != 1`, the system must fail-closed by raising `OptimisticLockError`.
5. **Premise 5 (Anti-Placebo Concurrency Testing)**: Placebo tests pass even if `AND version=?` is removed. To guarantee regression protection in Milestone M4, the test suite must implement mutation checks (Mutants M1 to M4) where omitting `WHERE version=?` or performing RAM-only checks causes tests to fail immediately.

---

## 3. Caveats

1. **Append-Only Tables Excluded**: `events` (event journal) and `checkpoints` are append-only. They do not have UPDATE statements and do not suffer from blind overwrites; they must remain append-only.
2. **Read-Only Investigation Bound**: As an Explorer agent, no product code in `scp/` or `tests/` has been modified. The probe script and analysis reports are quarantined in `.agents/explorer_p2_3/`.
3. **Worker Implementation Scope**: Adding `version` to `idempotency`, `leases`, and `queue_accounts` requires updating `TaskKernel._schema()` with `ALTER TABLE ... ADD COLUMN version INTEGER NOT NULL DEFAULT 1` to support existing databases without dropping data.

---

## 4. Conclusion

1. **Vulnerability Confirmed (GAP-02)**: Satellite tables in `TaskKernel` (`idempotency`, `leases`, and satellite data structures) suffer from critical blind overwrite vulnerabilities, leading to silent data corruption and zombie worker leases under concurrency.
2. **FA-09 Exploit Proven**: Real terminal execution of `probe_satellite_blind_overwrite.py` demonstrates 3/3 reproducible failure modes.
3. **Architecture Defined (M3)**:
   - Define `class OptimisticLockError(KernelError)` in `scp/task_kernel.py`.
   - Update `TaskKernel._schema()` to add `version INTEGER NOT NULL DEFAULT 1` to `idempotency`, `leases`, and `queue_accounts`.
   - Update all satellite `UPDATE` statements to use `WHERE ... AND version=?`.
   - Raise `OptimisticLockError` whenever `cur.rowcount != 1`.
4. **Anti-Placebo Strategy Ready (M4)**: 4 mutation kill scenarios designed in `tests/T04_kernel/test_satellite_occ_anti_placebo.py` to kill false green tests.

---

## 5. Verification Method

To independently reproduce and verify this investigation:

1. **Run the FA-09 Exploit Probe**:
   ```powershell
   python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py
   ```
   *Expected Result*: Output displays 3/3 probes crashing/raising `BlindOverwriteFlawError`, proving the current vulnerability.

2. **Inspect Analysis and Test Designs**:
   - View `c:\Users\check\Downloads\scp\.agents\explorer_p2_3\analysis.md` for full call graphs, mutant specifications, and SQL contracts.

3. **Post-Fix Invalidation Condition**:
   Once M3 implements OCC:
   ```powershell
   python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py --verify-fix
   ```
   Must catch `OptimisticLockError` and exit cleanly, proving that blind overwrites are completely blocked.
