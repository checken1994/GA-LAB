# SCP Reality Verifier (Local Copy)
Source: c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

Core Methodology:
- Evidence Levels:
  A: Static (syntax/file exists) - not runtime proof
  B: Integration (modules connect) - partial
  C: End-to-end (full pipeline passes) - workload specific
  D: Recovery proof (crash/restart handled)
- Independent postcondition verification: verify actual state changes, file contents, error codes.
- Do not accept claims without empirical test execution.
