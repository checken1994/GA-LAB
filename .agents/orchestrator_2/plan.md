# Execution Plan — Phase 2: GAP-02 OCC Blind Overwrites

## Mission Objective
Eliminate GAP-02 (OCC Blind Overwrites) in SCP Task Kernel satellite tables (`artifacts`, `task_events`, `journals`, etc.) by enforcing atomic optimistic concurrency control (`WHERE version=?` and `OptimisticLockError`) across `scp/kernel_storage.py` and all related DAOs.

## Plan Steps

### Step 1: Deep Survey & Call Graph Navigation (Parallel Explorers)
- **Explorer 1 (Call Graph & UPDATE Audit)**:
  - Generate a detailed line-by-line call graph / execution trace for `scp/kernel_storage.py` and associated DAO methods.
  - Catalog every `UPDATE` statement in the codebase, identifying which tables and columns are touched, and whether `WHERE version=?` is present or missing.
- **Explorer 2 (Schema, Invariant INV-01 & Architecture Review)**:
  - Inspect SQLite schema definitions, migrations, and model definitions for satellite tables (`artifacts`, `task_events`, `journals`, etc.).
  - Review how `OptimisticLockError` is defined and how Phase 1 handled OCC on `tasks`.
  - Propose exact schema adjustments and atomic transaction boundaries.
- **Explorer 3 (FA-09 Exploit Mandate Design)**:
  - Design an independent exploit/probe script simulating concurrent/blind overwrites on satellite tables.
  - Ensure the probe demonstrates data loss or race condition when OCC is missing, fulfilling FA-09 before any fix is applied.

### Step 2: Synthesis & Exploit Execution
- Synthesize findings from the three Explorers.
- Have Worker run the exploit script to confirm it crashes/reproduces the blind overwrite on current code.

### Step 3: Implementation & Atomic Enforcement (Worker)
- Dispatch Worker to:
  1. Update database schemas to include `version` on all satellite tables that undergo state updates.
  2. Update all `UPDATE` queries in `scp/kernel_storage.py` and DAOs to include `WHERE version=?` and increment version atomically.
  3. Raise `OptimisticLockError` when row count is 0.
  4. Verify the exploit probe is now caught and blocked by `OptimisticLockError`.
  5. Run mutation anti-placebo tests.
  6. Run `pytest tests/ -q` and `python tools/t00_meta_audit.py` and capture full raw terminal outputs.

### Step 4: Multi-Agent Review & Challenge
- **Reviewer 1 & 2**: Objectively review code diff, verify INV-01 atomic enforcement, check FA-01 through FA-10 compliance.
- **Challenger 1 & 2**: Adversarial stress testing, race condition simulation, mutation anti-placebo checks.
- **Forensic Auditor**: Check for zero hardcoded mocks, no fake logs, genuine DB-level enforcement.

### Step 5: Gate Evaluation & Final Handoff
- Evaluate `GATE_STATUS.md`.
- Ensure all acceptance criteria are met with verified terminal evidence.
- Send handoff report to caller.
