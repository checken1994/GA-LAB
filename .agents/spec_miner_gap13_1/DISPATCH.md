# DISPATCH — Spec Miner GAP-13 #1 (Probes, Causal Graph & Test Matrix)

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## PRE-SESSION MANDATE
You MUST call `view_file` on:
1. `c:\Users\check\Downloads\scp\GA.md`
2. `c:\Users\check\Downloads\scp\.agents\GEMINI.md`
3. `c:\Users\check\Downloads\scp\.agents\AGENTS.md`
4. `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
5. `c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md`

## Mission & Scope
Read `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` and `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`.
Your role: Read-only specification and test investigator. Do NOT modify source code files.
Investigate existing probes and test suite:
1. Review `tools/probes/` (e.g. `probe_gap11.py`, `probe_gap12_sabotage.py` or similar). How are probes structured in SCP to follow FA-09 & FA-12?
   - How should `tools/probes/probe_gap13_bypass.py` be designed?
   - What is the exploit vector? (Create task -> transition to WAITING_APPROVAL -> exploit calls `transition(task_id, "READY")` without token -> currently succeeds, proving GAP-13).
   - How will the probe verify RED before patch and GREEN after patch?
2. Review `tests/T04_kernel/test_adversarial_kernel_flaws.py` and other kernel test files:
   - What tests currently exist for GAP-11, GAP-12?
   - What callers in the codebase call `transition(..., "READY")`?
   - Construct the Mermaid Causal Graph for the Approval Gate (FA-12).
   - Construct the FA-13 Coverage Matrix for `commit_approval()` and the Approval Gate:
     * Unauthenticated bypass attempt (`transition(..., "READY")` from `WAITING_APPROVAL`) -> blocked (`InvalidTransition`).
     * Missing token / None token -> rejected.
     * Tampered / forged signature token -> rejected (`InvalidTokenSignatureError` / rejected).
     * Valid signature but wrong capability (lacks `approval:grant`) -> rejected.
     * Valid token for different task_id / scope -> rejected.
     * Expired token -> rejected.
     * Valid capability token with `approval:grant` -> accepted -> state becomes `READY`.
     * Valid operator signature -> accepted -> state becomes `READY`.
     * Task not in `WAITING_APPROVAL` (e.g. `CREATED`, `RUNNING`) calling `commit_approval()` -> rejected (`InvalidTransition`).
     * OCC conflict during `commit_approval()` -> rejected.
3. Output report to `c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_1\handoff.md`.

## 2026-09-08T02:07:22Z
Investigate probe designs in tools/probes/ (probe_gap11.py, probe_gap12_sabotage.py) and test suite in tests/T04_kernel/test_adversarial_kernel_flaws.py. Design the exploit probe tools/probes/probe_gap13_bypass.py following FA-09 & FA-12. Construct the full Mermaid Causal Graph for the Approval Gate and create the FA-13 Coverage Matrix covering all approval branches and callers.
Output your comprehensive findings to c:\Users\check\Downloads\scp\.agents\spec_miner_gap13_1\handoff.md and report back via send_message.

