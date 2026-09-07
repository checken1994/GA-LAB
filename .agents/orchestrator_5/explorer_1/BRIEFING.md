# BRIEFING — 2026-09-07T03:17:35Z

## Mission
Investigate HandsExecutor & CapabilityAuthority core flaws, anti-placebo probe execution, and design fail-closed fix strategy for FA-05 compliance.

## 🔒 My Identity
- Archetype: Explorer
- Roles: HandsExecutor & Authority Core Specialist
- Working directory: c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1
- Original parent: 967399d1-d666-4dce-899b-4c2468b6dd91
- Milestone: Orchestrator 5 Wave / Hands Authority Invariants Fix

## 🔒 Key Constraints
- Read-only investigation — do NOT implement production code
- Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-10 (no self-granting authority, no simulating PASS)
- Boundaries enforced at Database/Hardware level, not via RAM/Variables
- Single machine-readable contract compliance

## Current Parent
- Conversation ID: 967399d1-d666-4dce-899b-4c2468b6dd91
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `tools/probes/probe_hands_authority_flaws.py` (executed live; confirmed baseline failure RED on invariant checks)
  - `scp/hands/hands_executor.py` (lines 111, 326 fallback issuance, lines 68-77 _check_capability, lines 376-379 restore_capabilities)
  - `scp/security/capability_epoch.py` (validate signature, epoch and revocation checking, missing subject validation)
  - `scp/hands/task_kernel_bridge.py` (lines 99, 314, 338, 482 token dropping)
  - `scp/api/routes/hands_routes.py` (lines 38, 46 missing capabilityToken in request schemas)
  - `scp/hands/planner.py` (line 479 token dropping)
  - `tests/T09_golden_task/test_golden_a_agent_os.py` & `tests/T04_kernel/test_kernel_p1_regressions.py`
- **Key findings**:
  - Baseline empirically confirmed vulnerable: HandsExecutor mints its own token when capability_token is None (FA-05 violation).
  - Scope-blind validation: CapabilityAuthority.validate ignores subject, allowing read tokens to execute write actions (INV-AUTH-02 violation).
  - Calling chain drops capability_token at bridge, routes, and planner boundaries.
  - Fail-closed response for capability_token is None must return exact error format with zero driver side effects.
- **Unexplored areas**: None for this investigation phase.

## Key Decisions Made
- Executed empirical anti-placebo probe first, confirming RED on baseline and GREEN on guarded.
- Formulated concrete, fail-closed patch specifications across HandsExecutor, CapabilityAuthority, TaskKernelHandsBridge, HandsRoutes, and test migrations.
- Documented full findings and evolution strategy in handoff.md.

## Artifact Index
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1\DISPATCH.md — Dispatch log
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1\BRIEFING.md — Situational awareness
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1\progress.md — Progress heartbeat
- c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_1\handoff.md — 5-component handoff report
