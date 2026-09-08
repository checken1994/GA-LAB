---
name: scp-reality-verifier
description: Kiểm chứng claim và kết quả của SCP bằng evidence, postcondition, provenance và test profile; phân biệt static PASS với integration/end-to-end proof.
---

# SCP Reality Verifier (Local Copy for Forensic Auditor)

See .agents/skills/scp-reality-verifier/SKILL.md for original normative definition.
Key principles:
1. Evidence Hierarchy (Static -> Integration -> End-to-End -> Recovery proof)
2. PASS_WITHIN_SCOPE only
3. Never trust model self-reports; inspect physical execution, SQLite rows, raw stdout/stderr
