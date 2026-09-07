# Subagent Task: Probe Before Patch & Anti-Placebo Execution

You are Challenger 1 (`challenger_probe_1`).
Working Directory: `c:\Users\check\Downloads\scp\.agents\challenger_probe_1\`
Authoritative Request: `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` (read this file first).
Skills to consult:
- `c:\Users\check\Downloads\scp\.agents\skills\scp-delta-audit\SKILL.md`
- `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
- `c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md`

## 2026-09-06T17:57:34Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Challenger 1 (challenger_probe_1).
Your working directory is: c:\Users\check\Downloads\scp\.agents\challenger_probe_1\
Read the authoritative request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (specifically timestamp ## 2026-09-06T17:49:43Z).

FORCED SKILL ACTIVATION:
You MUST use view_file to read directly:
1. c:\Users\check\Downloads\scp\.agents\skills\scp-delta-audit\SKILL.md
2. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
3. c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md

BACKGROUND CONTEXT:
Read the prior reports:
- c:\Users\check\Downloads\scp\.agents\explorer_reality_scan_1\reality_scan_report.md
- c:\Users\check\Downloads\scp\.agents\spec_miner_invariants_1\target_manifest_and_gaps.md

MISSION — PHASE 4: PROBE BEFORE PATCH & MUTATION ANTI-PLACEBO TESTING:
Audit Target: `scp/hands/hands_executor.py` và cơ chế Cấp quyền (Authority/Capability).
Suspected Flaw: FA-05 violation ("Tử huyệt bạo chúa"): `HandsExecutor` self-issues a `CapabilityToken` if `capability_token is None`. Scope-blind validation accepts read tokens for write actions.

TASKS:
1. Create an executable probe script (e.g. `c:\Users\check\Downloads\scp\tools\probes\probe_hands_authority_flaws.py` or within your working directory).
2. The probe script must execute via `run_command` in Python and test:
   a) Sub-test 1: Self-Granting Authority reproduction (`HandsExecutor.execute("pc.write_file", ..., capability_token=None)`). Prove that file is written to disk without caller providing a token.
   b) Sub-test 2: Scope Confusion / Privilege Escalation (`HandsExecutor.execute("pc.write_file", ..., capability_token=token_for_pc_status)`). Prove that status token is accepted for write action.
   c) Sub-test 3: Mutation Anti-Placebo Verification. Per Phase 4 Anti-Placebo mandate:
      - Show that under Current Baseline Code, an invariant assertion (e.g. `assert result['success'] is False and not target_file.exists()`) FAILS with an AssertionError (Red), proving the vulnerability is live and exploitable.
      - Show that when an Invariant-Preserving Guard is simulated/applied (e.g. strict PEP checking `if capability_token is None: return False` and `token.subject == f"hands:{action}"`), the exact same assertion PASSES (Green). This proves the probe is sensitive and NOT a placebo!
3. Execute the probe script using `run_command` and capture actual raw stdout and stderr.
4. TUYỆT ĐỐI KHÔNG ĐƯỢC PHÉP SỬA CODE SẢN PHẨM (`scp/`) Ở GIAI ĐOẠN NÀY!
5. Write your comprehensive report to `c:\Users\check\Downloads\scp\.agents\challenger_probe_1\probe_execution_report.md` and complete your handoff report `c:\Users\check\Downloads\scp\.agents\challenger_probe_1\handoff.md`.
6. Send a message to orchestrator with summary and raw terminal outputs when done.

