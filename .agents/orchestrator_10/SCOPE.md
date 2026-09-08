# Scope: GAP-13 Remediation (Unauthenticated WAITING_APPROVAL Bypass)

## Architecture
- Core target: `scp/task_kernel_parts/taskkernel.py` (`TaskKernel`)
- Auth token target: `scp/core/capability_token.py` (`CapabilityToken`)
- Persistence: `scp/kernel_storage.py` (SQLite backend, OCC version fencing, event journaling)
- Probe target: `tools/probes/probe_gap13_bypass.py`
- Test target: `tests/T04_kernel/test_adversarial_kernel_flaws.py`
- Adversarial test target: `tests/T04_kernel/test_gap13_adversarial_challenge.py`, `tests/T04_kernel/test_gap13_state_machine_boundaries.py`

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | R1: Probe Before Patch | Exploit script `probe_gap13_bypass.py` running RED demonstrating WAITING_APPROVAL -> READY unauthenticated bypass | M1 | ORIGINAL_REQUEST.md § 2026-09-08T02:05:20Z | DONE (RED pre-patch, GREEN post-patch) |
| 2 | R2: Block Raw Approval Transition | `transition(task_id, "READY")` raises `InvalidTransition` if task in `WAITING_APPROVAL` | M1 | ORIGINAL_REQUEST.md § 2026-09-08T02:05:20Z | DONE (taskkernel.py:403-406) |
| 3 | R2: Secure `commit_approval()` | Implement `commit_approval()` requiring valid `CapabilityToken` with `approval:grant` or valid operator signature, DB-level verification, OCC fencing | M1 | ORIGINAL_REQUEST.md § 2026-09-08T02:05:20Z | DONE (taskkernel.py:1084-1182) |
| 4 | R3: Causal Test Coverage (FA-13) | Comprehensive adversarial test cases covering full causal tree of Approval Gate in `test_adversarial_kernel_flaws.py` (11 branches) | M1 | ORIGINAL_REQUEST.md § 2026-09-08T02:05:20Z | DONE (11/11 passing tests) |
| 5 | Regression & Meta-Audit | `pytest tests/ -q` 100% pass (571/571), `tools/t00_meta_audit.py` PASS, 0 skips, 0 xfails | M1 | ORIGINAL_REQUEST.md § 2026-09-08T02:05:20Z | DONE (0 regressions) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | GAP-13 Remediation | R1 (Probe RED) -> R2 (Block raw transition + commit_approval) -> R3 (Causal Tests) -> Multi-Agent Review & Challenge -> Forensic Audit | None | **DONE** |

## Interface Contracts
### `commit_approval()` in `TaskKernel`
- Signature: `commit_approval(self, task_id: str, approval_token: Any, actor: str = "operator", details: Optional[Dict[str, Any]] = None, expected_version: Optional[int] = None) -> TaskRecord`
- Preconditions:
  - Task exists and current state is `WAITING_APPROVAL` (or fail with `InvalidTransition`).
  - Task not in terminal state (`COMPLETED`, `FAILED`, `CANCELLED`).
  - Global kill switch not active (`KillSwitchActive`).
  - Approval token must be validated against `verify_approval_authority()`.
  - Token must possess `approval:grant` capability / scope matching task.
  - OCC version check: version matching in database update (`expected_version` matches `cur_version`).
- Postconditions:
  - State atomically transitions to `READY`.
  - Event `TASK_APPROVED` recorded in append-only journal with token signature reference and actor identity.
  - DB durability confirmed (WAL commit).

### Raw `transition(task_id, to_state)` Restriction
- If task state == `WAITING_APPROVAL` and `to_state == "READY"`:
  - Calling `transition(task_id, "READY")` directly without `commit_approval` strictly raises `InvalidTransition("direct transition from WAITING_APPROVAL to READY is forbidden; use commit_approval() with valid capability token")`.
