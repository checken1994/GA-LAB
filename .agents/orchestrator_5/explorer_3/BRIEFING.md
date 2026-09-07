# BRIEFING — 2026-09-07T03:20:00Z

## Mission
Analyze all tests affected by the GAP-07 HandsExecutor Self-Granting fix, identify tests that omit `capability_token`, and produce an exact zero-loosening migration map.

## 🔒 My Identity
- Archetype: explorer
- Roles: Test Suite Impact & Migration Specialist
- Working directory: c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3
- Original parent: 967399d1-d666-4dce-899b-4c2468b6dd91
- Milestone: GAP-07 HandsExecutor Self-Granting Authority Fix

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Zero-Trust and Fail-Closed principles; FA-01 through FA-10 compliance
- Strictly NO test deletion, NO skipping, NO xfail, NO loosening assertions (FA-01, FA-02)
- Zero-simulation of test PASS (FA-04, FA-08)

## Current Parent
- Conversation ID: 967399d1-d666-4dce-899b-4c2468b6dd91
- Updated: 2026-09-07T03:20:00Z

## Investigation State
- **Explored paths**: `tests/`, `scp/hands/`, `scp/security/capability_epoch.py`, `scp/api/routes/hands_routes.py`
- **Key findings**:
  1. Full test baseline established empirically: 441 passed in 106.57s.
  2. Exactly 3 tests across 2 test files call `HandsExecutor.execute` / `TaskKernelHandsBridge.execute`:
     - `tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_duplicate_request_returns_replayed_response`
     - `tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`
     - `tests/T09_golden_task/test_golden_a_agent_os.py::test_golden_a_agent_os_real_execution_flow`
  3. All 3 tests omit `capability_token` and will fail when self-granting is removed.
  4. Zero tests call `rollback()`, `POST /v3/hands/execute`, or `HandsPlanner.run_plan`.
  5. Exact migration strategy and Before/After code snippets documented in `handoff.md`.
- **Unexplored areas**: None within Explorer 3 problem boundary.

## Key Decisions Made
- Fully preserve all assertions (0 deletions, 0 skips, 0 xfails, 0 loosening).
- Migrated tests instantiate `CapabilityAuthority` as PDP, issue valid token for `hands:pc.write_file`, and pass it to `bridge.execute()`.
- Recommend adding `tests/T03_capability/test_hands_authority_pep.py` with 4 negative invariant tests.

## Artifact Index
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3\DISPATCH.md` — Initial dispatch message
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3\BRIEFING.md` — Agent briefing & situational awareness
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3\progress.md` — Progress tracker & liveness heartbeat
- `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3\handoff.md` — Comprehensive Handoff Report & Migration Map
