# Project: SCP Delta Audit
# Scope: GAP-12 (TaskKernel Unverified Terminal FAILED State Transition & Rogue Worker Sabotage)

## Target Subsystem Lock
- **Subsystem**: TaskKernel (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`, `scp/ask_kernel_adapter.py`)
- **Target Vulnerability**: GAP-12 — Unverified transition to `FAILED` & Rogue Worker Sabotage
- **Selection Rationale**:
  - Direct continuation of `EMERGENCY_GAP_REPORT.md` and `ORIGINAL_REQUEST.md` FA-13 coverage audit notes.
  - Sits at the core of SCP Task State Machine (governed by `scp-task-kernel-review` and `scp-dna`).
  - Symmetrical counterpart to GAP-11 (which blocked raw `COMPLETED`, but left raw `FAILED` unguarded).
  - Terminal state immutability means unverified transitions permanently sabotage tasks, bypassing retry policies, `max_attempts`, and recovery state machines.
  - 100% deterministically reproducible via standalone probe script without flaky sleep races.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Target Lock & Invariant Manifest | Formulate 4 essential invariants (INV-GAP12-01 to 04) | none | DONE |
| M2 | Reality Scan & Execution Path Trace | Line-by-line trace of failure paths in taskkernel.py and ask_kernel_adapter.py | M1 | DONE |
| M3 | Causal Gap Analysis (Mermaid) | Construct whole-system Mermaid graph distinguishing Current vs Required paths | M2 | IN_PROGRESS |
| M4 | Probe Execution & Anti-Placebo | Execute standalone probe via terminal, capture raw terminal evidence (FA-08, FA-09) | M3 | PLANNED |
| M5 | Evolution Path & 10-Section Report | Propose architectural remediation, review, forensic audit, compile handoff.md | M4 | PLANNED |

## Interface Contracts & Invariants
- `INV-GAP12-01` (Terminal State Evidence Invariant): A task shall NOT transition to `FAILED` without cryptographically valid or system-verified failure evidence / indictment attached.
- `INV-GAP12-02` (Lease Authority Invariant): A task in an active execution state (`RUNNING`, `VERIFYING`, `WAITING_TOOL`) shall NOT transition to `FAILED` without an active, unexpired lease and valid fencing token matching the current leaseholder.
- `INV-GAP12-03` (Pre-Execution Protection Invariant): A task in pre-execution state (`PLANNING`, `READY`, `QUEUED`) shall NOT be terminated into `FAILED` by arbitrary unauthenticated callers via `transition()`; unleased failures must require system administrative authority or be handled via `CANCELLED`.
- `INV-GAP12-04` (Non-Fatal Fault Recovery Invariant): Transient worker failures or exceptions during `RUNNING` must be routed through the recovery state machine (`UNKNOWN` -> `RECOVERING` -> `RECONCILING`), bounded by `max_attempts`, and cannot be forced directly to terminal `FAILED` to bypass retry mechanisms.
