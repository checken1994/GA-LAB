# Execution Plan — Phase 2: GAP-02 (OCC Blind Overwrites Elimination)

## Objective
Tiêu diệt hoàn toàn nguy cơ "Ghi đè mù" (Blind Overwrite) trên các bảng dữ liệu vệ tinh (`artifacts`, `task_events`, `journals`, v.v.) trong `scp/kernel_storage.py` và các DAO liên quan, đảm bảo mọi lệnh `UPDATE` đều tuân thủ OCC (`WHERE version=?`) và văng lỗi `OptimisticLockError` khi có xung đột (INV-01).

## Step-by-Step Verifiable Plan

### Step 1: Deep Exploration & Call Graph Navigation (3 Explorers)
- **Explorer 1** (`explorer_p2_1`):
  - Focus: Call Graph Navigation & Audit of all SQL UPDATE statements in `scp/kernel_storage.py` and related DAOs.
  - Deliverable: Detailed trace (`FileA:LineX -> FileB:LineY`) of every caller of UPDATE methods, catalog of existing UPDATE queries, WHERE clauses, and missing version checks.
- **Explorer 2** (`explorer_p2_2`):
  - Focus: Satellite Schema, Concurrency & Invariant INV-01 Architecture.
  - Deliverable: Schema analysis of all satellite tables (`artifacts`, `task_events`, `journals`, etc.), migration/schema evolution requirements for adding `version` columns, atomic transition enforcement.
- **Explorer 3** (`explorer_p2_3`):
  - Focus: Exploit Probe Design (FA-09) & Anti-Placebo Mutation Testing.
  - Deliverable: Concrete Python script design reproducing race condition/blind overwrite on satellite tables, and mutation test design.

### Step 2: Exploit Probe Execution & Proof of Vulnerability (FA-09)
- Worker runs the exploit probe script against the current codebase.
- Verify that terminal output captures raw exception/data loss/blind overwrite to satisfy FA-09 before applying fixes.

### Step 3: Atomic OCC Implementation (Worker)
- Add `version` column and OCC checking (`WHERE version = :expected_version`) to satellite tables in `scp/kernel_storage.py`.
- Raise `OptimisticLockError` on version mismatch (rows affected == 0).
- Update callers to provide and handle expected version.

### Step 4: Verification & Anti-Placebo Testing
- Verify exploit probe now fails-closed (detects collision and raises `OptimisticLockError`).
- Run Mutation Anti-Placebo test.
- Run full test suite: `pytest tests/ -q` and `python tools/t00_meta_audit.py`.

### Step 5: Multi-Agent Review & Forensic Audit Gate
- 2 Reviewers independently evaluate code quality, completeness, and interface contracts.
- 2 Challengers conduct stress testing and edge-case probing.
- 1 Forensic Auditor verifies compliance with FA-01 to FA-10.

### Step 6: Gate Verdict & Handoff
- Formulate GATE_STATUS.md and final handoff to parent.
