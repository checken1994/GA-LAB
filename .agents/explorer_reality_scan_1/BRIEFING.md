# BRIEFING — 2026-09-07T00:57:00Z

## Mission
Investigate HandsExecutor and Capability/Authority mechanics for FA-05 violations (self-granting authority/bypass PEP) and produce a detailed Call Graph and Reality Scan Report.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, reality scanner
- Working directory: c:\Users\check\Downloads\scp\.agents\explorer_reality_scan_1\
- Original parent: caaa4b09-e167-4a07-be9d-1e7c5a5c8a20
- Milestone: Phase 2 Reality Scan

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- TUYỆT ĐỐI KHÔNG SỬA CODE SẢN PHẨM!
- Strict Zero-Trust and Fail-Closed principles, adhering to FA-01 through FA-10
- Must establish line-by-line Call Graph navigation map
- Output must be self-contained in handoff.md and reality_scan_report.md

## Current Parent
- Conversation ID: caaa4b09-e167-4a07-be9d-1e7c5a5c8a20
- Updated: 2026-09-07T00:57:00Z

## Investigation State
- **Explored paths**: `scp/hands/hands_executor.py`, `scp/security/capability_epoch.py`, `scp/hands/task_kernel_bridge.py`, `scp/hands/planner.py`, `scp/api/routes/hands_routes.py`, `scp/pc_control/pc_controller.py`, `tests/T04_kernel/test_kernel_p1_regressions.py`, `tests/T09_golden_task/test_golden_a_agent_os.py`, `spec/protected_invariants.yaml`
- **Key findings**:
  1. FA-05 violation PROVEN: `HandsExecutor.execute` line 111 and `HandsExecutor.rollback` line 326 self-grant capability tokens when `capability_token=None`.
  2. PEP colocation: Executor instantiates writable `CapabilityAuthority` and exposes `restore_capabilities`, enabling self-healing from quarantine.
  3. Scope-blind validation: `CapabilityAuthority.validate` checks only epoch integer, ignoring subject/action/resource.
  4. Protocol disconnect: `HandsActionRequest`, `TaskKernelHandsBridge.execute`, and `HandsPlanner.run_plan` do not propagate tokens, forcing reliance on the self-granting backdoor.
  5. Validated via 3 live executable terminal probes (FA-09).
- **Unexplored areas**: None within the Phase 2 Reality Scan scope.

## Key Decisions Made
- Executed read-only verification probes in isolated temp directories without altering any product or test code.
- Constructed complete line-by-line Call Graph across API, Planner, Bridge, and Executor layers.
- Formatted output according to Delta Audit Output Contract & 5-Component Handoff Protocol.

## Artifact Index
- DISPATCH.md — Incoming task dispatch record
- BRIEFING.md — Agent identity and working memory
- progress.md — Heartbeat and step-by-step progress
- reality_scan_report.md — Comprehensive Phase 2 Reality Scan report
- handoff.md — 5-component hard handoff report
