# BRIEFING — 2026-09-08T01:27:00Z

## Mission
Read-only investigation of downstream callers of TaskKernel.transition(..., "FAILED") across scp/, specifically scp/ask_kernel_adapter.py, scp/hands/task_kernel_bridge.py, and all other call sites, to prepare migration to kernel.commit_failed().

## 🔒 My Identity
- Archetype: Teamwork explorer (teamwork_preview_explorer)
- Roles: Explorer, Investigator, Synthesizer
- Working directory: c:\Users\check\Downloads\scp\.agents\explorer_2
- Original parent: f1e50da6-b37c-427b-a8a3-fdc334188734
- Milestone: Orchestrator 9 Downstream Callers Audit

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strictly bound by Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-13
- FORBIDDEN from self-granting authority or simulating PASS results
- Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables
- Use send_message to report back to parent (f1e50da6-b37c-427b-a8a3-fdc334188734)

## Current Parent
- Conversation ID: f1e50da6-b37c-427b-a8a3-fdc334188734
- Updated: 2026-09-08T01:27:00Z

## Investigation State
- **Explored paths**:
  - `scp/ask_kernel_adapter.py`: line 426-447 (`fail()` method) and line 505 (`run_rag()`)
  - `scp/hands/task_kernel_bridge.py`: line 445 (policy denial before dispatch) and line 582 (pre-dispatch failure fallback)
  - `scp/task_kernel_parts/taskkernel.py`: lines 250-365 (`transition()`), lines 464-480 (`_assert_lease()`), lines 919-951 (`commit_completed()`)
  - `tests/T04_kernel/test_adversarial_kernel_flaws.py`: lines 886-892 (adapter.fail test)
  - `tests/T03_capability/test_hands_authority_pep.py`: lines 207, 252, 283 (bridge failure assertions)
  - Full codebase scan across `scp/`, `tests/`, and `tools/`
- **Key findings**:
  - Exactly 3 call sites call `transition(..., "FAILED")` in entire `scp/` codebase:
    1. `scp/ask_kernel_adapter.py:430` in `fail()`
    2. `scp/hands/task_kernel_bridge.py:445` in `execute()`
    3. `scp/hands/task_kernel_bridge.py:582` in `execute()`
  - In `AskKernelAdapter`, active lease is owned by worker `"ask-route-worker"`, but current call passes `actor="ask-kernel-adapter"`. Must pass `actor="ask-route-worker"` to satisfy `_assert_lease` actor verification.
  - In `TaskKernelHandsBridge`, active lease is owned by `self.worker_id` (`"hands-route-worker"`), but current call passes `actor="hands-kernel-bridge"`. Must pass `actor=self.worker_id`.
  - Zero direct calls to `transition(..., "FAILED")` exist in `tests/` (they only test via `adapter.fail` and `bridge.execute`).
- **Unexplored areas**: None for downstream callers scope. Full universe mapped.

## Key Decisions Made
- Fully audited all downstream callers and formulated exact `commit_failed()` invocation contracts.

## Artifact Index
- c:\Users\check\Downloads\scp\.agents\explorer_2\BRIEFING.md — Persistent working memory
- c:\Users\check\Downloads\scp\.agents\explorer_2\DISPATCH.md — Dispatch log
- c:\Users\check\Downloads\scp\.agents\explorer_2\progress.md — Liveness heartbeat
- c:\Users\check\Downloads\scp\.agents\explorer_2\handoff.md — Final handoff report
