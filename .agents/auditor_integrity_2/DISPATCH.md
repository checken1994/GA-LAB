# Task Assignment: Forensic Auditor 2

## Identity
- Role: Forensic Auditor (Integrity Forensics & FA-01..FA-07 Verifier)
- Archetype: teamwork_preview_auditor
- Working directory: c:\Users\check\Downloads\scp\.agents\auditor_integrity_2
- Parent: Orchestrator 2 (c:\Users\check\Downloads\scp\.agents\orchestrator_2)

## Mandatory Input
- Read ORIGINAL_REQUEST.md at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (entry dated 2026-09-05T10:20:22Z).
- Primary Deliverables & Codebase to Audit:
  - Deliverable: c:\Users\check\Downloads\scp\teamwork_runtime_audit_report.md
  - Repository: c:\Users\check\Downloads\scp
- Apply skills:
  - c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
  - c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md
  - c:\Users\check\Downloads\scp\.agents\skills\scp-release-evidence-gate\SKILL.md

## Objective & Scope
Perform an independent forensic integrity audit of the audit deliverable and process:
1. Audit against FA-01 (Assertion Weakening): Ensure no assertions were loosened or weakened.
2. Audit against FA-02 (Test Deletion/Skips): Ensure no tests were deleted, skipped, or xfailed to produce green reports.
3. Audit against FA-03 (Evidence Fabrication): Ensure terminal outputs, logs, SHAs, and test counts in `teamwork_runtime_audit_report.md` are genuine and match the exact tested snapshot `48e5ca8dd0867d1257103ea66f73be752d785b60`.
4. Audit against FA-04 (Manufactured Verified): Ensure no simulated, stubbed, or fake VERIFIED assertions were used to manufacture green verdicts.
5. Audit against FA-05 (Self-Granting Authority): Ensure capability boundaries were respected.
6. Audit against FA-06 (Unreconciled Mutation): Ensure no production code was modified (read-only audit mode).
7. Audit against FA-07 (Maturity Claim): Ensure no unwarranted production-readiness or maturity claims were made (the report appropriately assigns CANDIDATE_NOT_PROVEN).
8. Deliver a definitive forensic verdict: `CLEAN` or `INTEGRITY VIOLATION`.

## Output Requirements
Write a comprehensive forensic report to `c:\Users\check\Downloads\scp\.agents\auditor_integrity_2\handoff.md` with explicit Verdict (`CLEAN` or `INTEGRITY VIOLATION`).
Notify orchestrator when done via send_message.
