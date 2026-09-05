# SCP Runtime Audit (Local Copy)
Source: c:\Users\check\Downloads\scp\.agents\skills\scp-runtime-audit\SKILL.md

Key Methodology:
- Evaluate SCP by observable evidence, not module counts or test PASS numbers.
- Differentiate static assertion, integration proof, and end-to-end runtime proof.
- Verify exact Git SHA, status, runtime version, launcher/runner hash.
- Service inventory & port alignment check.
- Test runner credibility: verify collection, encoding, reproducibility, actual service execution.
- Golden task evidence search (planner -> policy -> tool -> observation -> verifier -> audit -> artifact).
- Guard checks: deny-by-default, fail-closed startup, egress deny, secret redaction, kill switch.
- Classification of findings: BLOCKER, HIGH, MEDIUM, LOW.
- Final runtime status: NOT_RUNNING, PARTIALLY_RUNNING, CANDIDATE_NOT_PROVEN, RUNTIME_PROVEN.
