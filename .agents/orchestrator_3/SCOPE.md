# Scope: Phase 2 — GAP-02 (OCC Blind Overwrites Elimination)

## Architecture
- **Target Modules**: `scp/kernel_storage.py`, `scp/task_kernel.py`, satellite DAOs.
- **Satellite Tables Under Scope**: `artifacts`, `task_events`, `journals`, `idempotency_keys`, `leases`, and any other tables modified via UPDATE.
- **Core Invariant**: INV-01 (Atomic OCC Fencing) — every UPDATE must have `WHERE version=?` (or equivalent OCC guard) and raise `OptimisticLockError` if row count == 0.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | SQL UPDATE Catalog & Call Graph | Complete inventory of all UPDATE statements in storage layer and their caller call graph | M1 | DISPATCH.md R1 & User Directive |
| 2 | Satellite Schema Versioning | Schema definition with `version` integer column across satellite tables | M1/M2 | DISPATCH.md R1/R2 |
| 3 | Exploit Probe Script (FA-09) | Standalone script demonstrating blind overwrite on satellite table without OCC | M2 | DISPATCH.md Acceptance Criteria & FA-09 |
| 4 | OCC Implementation | Code changes implementing `WHERE version=?` and raising `OptimisticLockError` | M3 | DISPATCH.md R1/R2 |
| 5 | Mutation Anti-Placebo | Tests demonstrating that disabling OCC check immediately fails tests | M4 | DISPATCH.md R3 |
| 6 | Full Test & Meta-Audit | `pytest tests/ -q` PASS and `python tools/t00_meta_audit.py` PASS | M4 | DISPATCH.md Acceptance Criteria |
| 7 | Multi-Agent Review & Forensic Gate | 2 Reviewers, 2 Challengers, 1 Forensic Auditor | M5 | Project Pattern §2B |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Deep Survey & Call Graph Audit | Catalog all UPDATE queries & map callers line-by-line | none | DONE |
| M2 | Exploit Probe & Reproduction | Create and execute exploit probe reproducing vulnerability (FA-09) | M1 | DONE |
| M3 | OCC Implementation | Enforce atomic version checking in `kernel_storage.py` and callers | M2 | DONE |
| M4 | Anti-Placebo & Full Verification | Mutation testing + full regression test suite + meta-audit | M3 | DONE |
| M5 | Adversarial Review & Forensic Gate | Multi-agent gate (Reviewers, Challengers, Auditor) | M4 | DONE |

## Interface Contracts
### Storage Layer ↔ Kernel Callers
- Method signatures updating satellite entities must accept `expected_version: int`.
- If update matches 0 rows due to version mismatch, raise `OptimisticLockError`.
- Upon successful update, returned object or record reflects `version + 1`.
