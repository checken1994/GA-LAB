# DISPATCH — ORCHESTRATOR 10 (GAP-13 REMEDIATION)

## Mission
Audit and patch GAP-13 (Unauthenticated WAITING_APPROVAL Bypass) in TaskKernel per SCP Zero-Trust process with Empirical Causal Closure (FA-12 & FA-13).

## Working Directory
`c:\Users\check\Downloads\scp\.agents\orchestrator_10`

## Authoritative User Request
See `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` (entry under `## 2026-09-08T02:05:20Z`).

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

PRE-SESSION MANDATE: BẮT BUỘC dùng tool `view_file` để tải `GA.md`, `.agents/GEMINI.md` và `.agents/AGENTS.md` ngay lập tức để nạp đầy đủ các nguyên tắc từ FA-01 đến FA-13 vào context.
Skill requirement: Tải `.agents/skills/scp-dna/SKILL.md` và `.agents/skills/scp-task-kernel-review/SKILL.md`.

## Key Objectives & Requirements
1. **R1. Probe Before Patch (FA-12)**:
   - Write script `probe_gap13_bypass.py` (or in `tools/probes/probe_gap13_bypass.py`) demonstrating that GAP-13 exists: an attacker can transition a task from `WAITING_APPROVAL` to `READY` directly without any approval token.
   - Script MUST run RED before code modification.

2. **R2. Restrict Unauthenticated Approval**:
   - In `scp/task_kernel_parts/taskkernel.py`, block calling `transition(task_id, "READY")` directly if the task is in `WAITING_APPROVAL` without valid approval evidence (raise `InvalidTransition`).
   - Implement a secure approval mechanism (e.g., `commit_approval(task_id, approval_token, ...)` or equivalent) requiring verification of a valid `CapabilityToken` with `approval:grant` permission or valid operator signature. Ensure OCC version fencing and database-level durability.

3. **R3. Causal-Driven Test Coverage (FA-13)**:
   - Update `tests/T04_kernel/test_adversarial_kernel_flaws.py` (or dedicated test suite).
   - Create adversarial tests covering the entire Causal Graph for the Approval Gate.
   - Prove all bypass, forgery, and invalid capability token attempts fail closed.
   - Strictly adhere to FA-01 and FA-02 (no deleting, skipping, xfailing, or loosening tests).

4. **Acceptance Criteria**:
   - `pytest tests/ -q` passes 100% (0 skips, 0 xfails, exit code 0).
   - `python tools/t00_meta_audit.py` PASS (0 regressions).
   - Probe runs on live physical SQLite and turns GREEN (exploit vector blocked).
   - Full Handoff report in `.agents/orchestrator_10/handoff.md`.
