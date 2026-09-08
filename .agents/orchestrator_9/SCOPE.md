# Scope: Milestone M1 — GAP-12 Remediation & Causal Empirical Closure

## Architecture
- Subsystem: `TaskKernel` (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`)
- Adapters & Bridges: `scp/ask_kernel_adapter.py`, `scp/hands/task_kernel_bridge.py`
- Test Suites & Probes: `tests/T04_kernel/test_adversarial_kernel_flaws.py`, `tools/probes/probe_gap12_delta_audit.py`

## Requirements Mapping
| # | Requirement | Target File(s) | Description |
|---|---|---|---|
| R1 | Restrict Direct FAILED Transitions | `scp/task_kernel_parts/taskkernel.py` | In `transition()`, block direct transitions to `FAILED` (raising `InvalidTransition`). State transition to FAILED must strictly pass through `commit_failed()`. |
| R2 | Introduce `commit_failed()` Endpoint | `scp/task_kernel_parts/taskkernel.py` | Implement `commit_failed(self, task_id, lease_id, actor, failure_classification, indictment_ref, details)` validating lease & actor, checking retry budget, and committing failure/retry to DB. |
| R3 | Migrate Downstream Callers | `scp/ask_kernel_adapter.py`, `scp/hands/task_kernel_bridge.py` | Update `fail()` in `AskKernelAdapter` and error transitions in `TaskKernelBridge` to call `commit_failed()`. Ensure full backward compatibility. |
| R4 | Causal-Driven Test Coverage (FA-13) | `tests/T04_kernel/test_adversarial_kernel_flaws.py` | Comprehensive test coverage for `commit_failed()` branches (retryable vs exhausted) and updated callers. Ensure 100% test pass. |

## Invariants Preserved
- `INV-GAP12-01`: Direct transition to `FAILED` forbidden; must use `commit_failed()`.
- `INV-GAP12-02`: Mandatory indictment ref and failure details persisted in SQLite events and tasks tables.
- `INV-GAP12-03`: Preservation of retry budget (`attempts < max_attempts`) routing to `UNKNOWN`/`RETRY_SCHEDULED`.
- `INV-GAP12-04`: Strict lease and actor verification in `_assert_lease()` and `commit_failed()`.

## Code Layout & Boundaries
- `scp/task_kernel_parts/taskkernel.py`: State machine transition guard and `commit_failed` definition.
- `scp/ask_kernel_adapter.py`: Adapter layer caller update.
- `scp/hands/task_kernel_bridge.py`: Hands bridge caller update.
- `tests/T04_kernel/`: Test suites.

## Acceptance Criteria
- `pytest tests/ -q` PASS 100% (no skip/xfail).
- `python tools/t00_meta_audit.py` PASS (0 regressions).
- Probe `probe_gap12_delta_audit.py` passes with `ALL_VECTORS_PROTECTED_GREEN`.
