# Task Assignment: Explorer Survey 2

## Identity
- Role: Explorer (Technical Debt, FA-02 Skips & EvidenceStore Lifecycle Specialist)
- Archetype: teamwork_preview_explorer
- Working directory: c:\Users\check\Downloads\scp\.agents\explorer_survey_2
- Parent: Orchestrator 2 (c:\Users\check\Downloads\scp\.agents\orchestrator_2)

## Mandatory Input
- Read ORIGINAL_REQUEST.md at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (specifically the entry dated 2026-09-05T10:20:22Z).
- Apply skills:
  - c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
  - c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

## Objective & Scope
1. Investigate the codebase for FA-02 skip paths and baseline technical debt:
   - Identify all `@pytest.mark.skip`, `@pytest.mark.xfail`, `pytest.skip()`, commented-out assertions, loosened assertions, or hidden bypasses in `tests/` and core tools.
   - Trace the causal chain: Trigger/Input -> Test Execution -> Bypass/Skip Encountered -> Technical Debt Masking -> False Green or Silenced Failure.
2. Investigate the Epistemic EvidenceStore:
   - Locate the EvidenceStore implementation and tests in the codebase.
   - Map its crash-ordering, atomic staging, journal append, write barrier/fsync, and recovery lifecycle.
   - Trace the causal chain: Event/Observation -> Staging -> Flush/Write -> Crash Boundary -> Recovery / Reconcile -> Verification.
   - Determine whether the crash-ordering guarantees are sound or if there are race conditions, uncommitted state leaks, or corruption vectors.
3. Provide concrete file paths, line numbers, and architectural insights.

## Output Requirements
Write a comprehensive structured report to `c:\Users\check\Downloads\scp\.agents\explorer_survey_2\handoff.md` and `progress.md`.
Include Observation, Logic Chain, Caveats, Conclusion, and Verification Method.
Notify orchestrator when done via send_message.

## 2026-09-05T10:21:55Z
Received dispatch from user/parent:
Investigate:
1. FA-02 skip paths and baseline technical debt in c:\Users\check\Downloads\scp: find all @pytest.mark.skip, @pytest.mark.xfail, pytest.skip(), commented assertions, loosened assertions in tests/ and tools/. Trace causal chain: Trigger/Input -> Test Execution -> Bypass/Skip -> Technical Debt Masking -> False Green.
2. Epistemic EvidenceStore lifecycle: crash-ordering, atomic staging, journal append, write barriers/fsync, and crash recovery. Trace causal chain: Event/Observation -> Staging -> Flush/Write -> Crash Boundary -> Recovery / Reconcile -> Verification.
