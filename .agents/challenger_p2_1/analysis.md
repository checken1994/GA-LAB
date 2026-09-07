# Adversarial Stress Testing & Concurrency Analysis Report (GAP-02)

> **Agent**: Challenger P2-1 (`empirical challenger`)  
> **Role**: critic, specialist  
> **Working Directory**: `c:\Users\check\Downloads\scp\.agents\challenger_p2_1`  
> **Parent Orchestrator**: `orchestrator_3` (Conv ID: `4aab71c9-e6ee-472b-8c41-c64e48735a24`)  
> **Target**: TaskKernel Satellite Tables OCC & Blind Overwrite Resolution  
> **Date**: 2026-09-07  
> **Verdict**: **APPROVE** (Production Code & Anti-Placebo Test Suite)  

---

## 1. Executive Summary

Challenger P2-1 conducted an empirical adversarial stress test of the TaskKernel Satellite Optimistic Concurrency Control (OCC) implementation authored by Worker P2-1.

### Key Empirical Findings:
1. **Explorer Probe Defect Identified**: The probe script `.agents/explorer_p2_3/probe_satellite_blind_overwrite.py` does NOT implement the `--verify-fix` flag claimed in Explorer P2-3's handoff. It completely ignores CLI arguments and executes raw SQL queries directly on `kernel.conn` (bypassing the Python TaskKernel API), which naturally continues to simulate blind overwrites.
2. **Independent Concurrency Stress Probe Passed (6/6)**: Challenger P2-1 created and executed an independent multi-threaded stress probe (`.agents/challenger_p2_1/probe_concurrency_stress.py`) testing actual `TaskKernel` OCC APIs under high thread contention (up to 20 concurrent racing threads). All 6 test vectors passed cleanly:
   - Exactly 1 winner in 20-thread race on `idempotency_complete`; 19 failed-closed with `OptimisticLockError`.
   - Exactly 1 winner in 20-thread race on RETRYABLE `idempotency_claim`; 19 failed-closed with `OptimisticLockError`.
   - Exactly 1 winner in 10-thread race on `release`; 9 failed-closed.
   - Heartbeat on released lease and stale heartbeat fail-closed with `OptimisticLockError`.
   - Atomic resolution between concurrent `heartbeat` and `expire_leases` verified.
3. **Anti-Placebo & Regression Test Pass**:
   - `pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`: 7 passed in 0.88s.
   - `pytest tests/T04_kernel/ -q`: 42 passed in 5.09s.
4. **Meta-Audit Gate Pass**:
   - `python tools/t00_meta_audit.py`: 0 new regressions, all integrity checks passed.

---

## 2. Adversarial Probe Evaluation: Explorer P2-3 Script vs Reality

### Forensic Inspection of `probe_satellite_blind_overwrite.py`
The orchestrator dispatch instructed:
> "Run the exploit probe with verify-fix flag: `python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py --verify-fix`. Verify all 3 vectors now fail-closed and catch OptimisticLockError."

When executed on the terminal:
```
python .agents/explorer_p2_3/probe_satellite_blind_overwrite.py --verify-fix
```
The script output showed 3/3 vulnerabilities reproduced, exiting with code 0.

### Root-Cause of Explorer Probe Behavior
Inspection of `.agents/explorer_p2_3/probe_satellite_blind_overwrite.py` revealed:
1. **No Argument Parsing**: The script has no `argparse` or `sys.argv` inspection. Any CLI argument (`--verify-fix`) is discarded.
2. **Raw SQL Bypass**:
   - In Probe 1 (lines 78-81): The probe directly invokes raw SQL:
     ```python
     cur = kernel.conn.execute(
         "UPDATE idempotency SET result_ref=? WHERE logical_key=?",
         (stale_ref, logical_key),
     )
     ```
     This bypasses `kernel.idempotency_complete(...)` entirely.
   - In Probe 2 (lines 126-130): The probe directly invokes:
     ```python
     cur = kernel.conn.execute(
         "UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?",
         (now, new_expires, lease.lease_id),
     )
     ```
     This bypasses `kernel.heartbeat(...)` entirely.
   - In Probe 3 (lines 157-195): The probe creates a custom SQLite table `artifacts` that does not exist in `TaskKernel._schema()`.
3. **Conclusion on Explorer Script**: Explorer P2-3 wrote an exploit demonstration for Milestone M2, but failed to deliver the `--verify-fix` mode. Per FA-09 and DNA #26 (Reality over Model), Challenger P2-1 rejects using this script for post-fix verification and designed an independent stress harness.

---

## 3. Independent Concurrency Stress Harness (`probe_concurrency_stress.py`)

To stress-test the actual production implementation in `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py`, Challenger P2-1 implemented `.agents/challenger_p2_1/probe_concurrency_stress.py`.

### Stress Test Matrix & Terminal Evidence

| # | Stress Test Scenario | Thread / Worker Model | Expected Outcome | Terminal Result | Verdict |
|---|----------------------|-----------------------|------------------|-----------------|---------|
| 1 | Idempotency API OCC Fencing | Single-thread stale worker (`expected_version=1` after bump to 2) | Stale update raises `OptimisticLockError(table="idempotency", entity_id=key, expected_version=1)` | Caught `OptimisticLockError`, DB content uncorrupted | PASS |
| 2 | Lease Heartbeat & Release OCC Fencing | Stale heartbeat (`expected_version=99`) and late heartbeat on released lease (`released=1`) | Both calls fail-closed raising `OptimisticLockError(table="leases")` | Caught `OptimisticLockError` on both checks | PASS |
| 3 | 20-Thread Idempotency Completion Race | 20 synchronized threads releasing simultaneously via `threading.Barrier(20)` on separate DB connections | Exactly 1 thread completes; 19 threads raise `OptimisticLockError` | `1 winner(s), 19 OptimisticLockError(s)` | PASS |
| 4 | 20-Thread RETRYABLE Claim Race | 20 synchronized threads racing on `idempotency_claim` with `expected_version=1` on RETRYABLE key | Exactly 1 claim succeeds; 19 threads raise `OptimisticLockError` | `1 claim(s), 19 OptimisticLockError(s)` | PASS |
| 5 | 10-Thread Lease Release Race | 10 synchronized threads calling `kernel.release(...)` with `expected_version=1` | Exactly 1 release succeeds; 9 threads raise `OptimisticLockError` or `StaleLease` | `1 winner(s), 9 conflict error(s)` | PASS |
| 6 | Concurrent Heartbeat vs `expire_leases` | 1 worker thread heartbeating racing against watchdog calling `expire_leases` | Either heartbeat wins or expire wins; no split-brain or unhandled exception | Observed `['expire_won', 'heartbeat_rejected_occ']`, DB version >= 2 | PASS |

### Raw Terminal Output Evidence:
```
================================================================================
ADVERSARIAL CONCURRENCY & STRESS PROBE — CHALLENGER P2-1
================================================================================
  [Stress Test 1] Testing Idempotency API OCC fencing...
  [Stress Test 1] PASS: Idempotency OCC fencing verified.
  [Stress Test 2] Testing Lease Heartbeat & Release API OCC fencing...
  [Stress Test 2] PASS: Lease Heartbeat & Release OCC fencing verified.
  [Stress Test 3] Running 20-thread concurrency race on Idempotency completion...
  [Stress Test 3] Results: 1 winner(s), 19 OptimisticLockError(s)
  [Stress Test 3] PASS: Exactly 1 winner in 20-thread race; 19 failed-closed with OptimisticLockError.
  [Stress Test 4] Running 20-thread concurrency race on RETRYABLE claim...
  [Stress Test 4] Claims: 1 claim(s), 19 OptimisticLockError(s)
  [Stress Test 4] PASS: Exactly 1 claimer in 20-thread race; 19 failed-closed with OptimisticLockError.
  [Stress Test 5] Running 10-thread concurrency race on Lease release...
  [Stress Test 5] Releases: 1 winner(s), 9 conflict error(s)
  [Stress Test 5] PASS: Exactly 1 release winner; 9 failed-closed.
  [Stress Test 6] Running race between Lease Heartbeat and expire_leases...
  [Stress Test 6] Events observed: ['expire_won', 'heartbeat_rejected_occ']
  [Stress Test 6] PASS: Atomic resolution between heartbeat and expiry verified.

================================================================================
ALL 6 ADVERSARIAL CONCURRENCY & OCC STRESS PROBES PASSED CLEANLY.
================================================================================
```

---

## 4. Verification of Anti-Placebo Suite and Integrity Guardrails

### 1. Anti-Placebo Test Suite (`pytest tests/T04_kernel/test_satellite_occ_anti_placebo.py -v`)
- Output: `7 passed in 0.88s`
- Verified test coverage:
  * `test_anti_placebo_exception_hierarchy_and_exports`: Verified `OptimisticLockError` inherits from `StaleLease` and `KernelError`.
  * `test_anti_placebo_idempotency_stale_update_fails_closed`: Mutant M1 killed.
  * `test_anti_placebo_lease_heartbeat_and_release_conflict_fails_closed`: Mutants M1 & M3 killed.
  * `test_anti_placebo_concurrent_racing_workers_exactly_one_winner`: Mutant M2 killed.
  * `test_anti_placebo_idempotency_claim_retryable_occ`: Mutant M4 killed.
  * `test_anti_placebo_tasks_claim_next_deadline_occ_fenced`: Fenced deadline cleanup killed residual blind overwrite.
  * `test_anti_placebo_schema_evolution_preserves_legacy_database`: Backward compatibility verified without data loss.

### 2. Full TaskKernel Suite (`pytest tests/T04_kernel/ -q`)
- Output: `42 passed in 5.09s`
- Zero regressions across core task kernel functionality.

### 3. Meta-Audit Guardrails (`python tools/t00_meta_audit.py`)
- Output: `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`
- Zero FA violations. No weakened assertions, no deleted/skipped/xfailed tests.

---

## 5. Formal Verdict

**VERDICT: APPROVE**

The implementation in `scp/task_kernel.py` and `scp/task_kernel_parts/taskkernel.py` satisfies all requirements of Milestone M3 and Invariant INV-01:
- Every mutation to mutable satellite tables (`idempotency`, `leases`, `queue_accounts`) is guarded by atomic version checks at the database layer.
- Version mismatches consistently raise `OptimisticLockError(table=..., entity_id=..., expected_version=...)`.
- Concurrency stress testing with 20 parallel threads proved zero blind overwrites and strict single-winner isolation.
- Schema evolution safely accommodates legacy SQLite databases.
