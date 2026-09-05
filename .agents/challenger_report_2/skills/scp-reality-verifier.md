# SCP Reality Verifier (Local Copy)
Source: c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

Key Methodology:
- Reality > Model: Do not trust model self-reporting. Verify observable results, pre/postconditions, provenance, and test profile.
- Evidence levels:
  A - Static (files/patterns exist, no runtime proof)
  B - Integration (some modules connected, partial runtime)
  C - End-to-end (full task through planner, policy, tool, verifier, audit)
  D - Recovery proof (level C + crash/timeout handling proven)
- PASS != TRUE: PASS only means no failure in test scope.
- Verdicts: VERIFIED, CONTRADICTED, INSUFFICIENT, UNKNOWN.
