# BRIEFING — 2026-09-08T02:15:00Z

## Mission
Investigate CapabilityToken and cryptographic verification in scp/core/capability_token.py and related modules to design secure approval token verification in TaskKernel without self-granting authority (FA-05).

## 🔒 My Identity
- Archetype: explorer
- Roles: read-only investigator, cryptosystem analyst
- Working directory: c:\Users\check\Downloads\scp\.agents\explorer_gap13_2
- Original parent: 6c4f4b5d-80a9-4083-87c8-3858c1af90bc
- Milestone: GAP-13 Investigation (CapabilityToken & Cryptographic Verification)

## 🔒 Key Constraints
- Read-only investigation — do NOT modify production code or tests
- Fail-Closed by default (Zero-Trust)
- FA-01 to FA-13 strict adherence
- FA-05: NO self-granting authority (Executor does not issue token; caller/authority issues token)
- Database/Hardware level boundary enforcement, not RAM/Variables

## Current Parent
- Conversation ID: 6c4f4b5d-80a9-4083-87c8-3858c1af90bc
- Updated: 2026-09-08T02:15:00Z

## Investigation State
- **Explored paths**: GA.md, GEMINI.md, AGENTS.md, scp-dna/SKILL.md, scp-task-kernel-review/SKILL.md, ORIGINAL_REQUEST.md, orchestrator_10/SCOPE.md, scp/core/capability_token.py, scp/security/capability_epoch.py, scp/task_kernel_parts/taskkernel.py, scp/task_kernel.py, tests/T03_capability/, tests/T04_kernel/test_adversarial_kernel_flaws.py, tools/probes/probe_gap12_gap13_unproven_vulnerabilities.py, PROJECT.md, .env.example, tests/conftest.py.
- **Key findings**:
  1. `CapabilityToken` uses deterministic HMAC-SHA256 signing and constant-time verification over `f"{subject}:{epoch}:{token_id}:{issued_at:.6f}"` with `SCP_CAPABILITY_SECRET`.
  2. `mint_token` and `verify_token` in `scp/core/capability_token.py` provide compact string token verification with scope, cap, and exp.
  3. `approval:grant` capability can be scoped globally or to a specific task (`f"approval:grant:{task_id}"`).
  4. Operator signature in SCP is an HMAC-SHA256 digest over canonical payload `f"operator_approval:{task_id}:{actor}:{timestamp:.6f}"`.
  5. In `TaskKernel`, raw `transition(task_id, "READY")` from `WAITING_APPROVAL` must raise `InvalidTransition`.
  6. In `commit_approval(task_id, approval_token, actor, details, expected_version)`, TaskKernel acts strictly as verifier (FA-05 compliant), validating external tokens fail-closed and committing state change with SQLite OCC version fencing and append-only journal logging.
- **Unexplored areas**: None within assigned scope; complete evidence chain established.

## Key Decisions Made
- Designed unified `verify_approval_authority()` supporting both `CapabilityToken` formats and operator signatures.
- Formulated complete `commit_approval()` and raw `transition()` guard contracts.
- Documented full findings in `handoff.md`.

## Artifact Index
- c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\DISPATCH.md — Task instructions and prompts
- c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\BRIEFING.md — Persistent awareness state
- c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\progress.md — Liveness heartbeat
- c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md — Final analysis report
