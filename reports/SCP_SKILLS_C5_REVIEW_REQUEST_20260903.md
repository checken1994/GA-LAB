# SCP Skills C5 Independent Review Request

Source SHA under review: `c8710387522cb9d43fbf746461e8cc51bc56a71f`.

Purpose: obtain an external review of the 13 SCP Skills and the pack-wide C1–C6 verification harness without relying on the generator's self-report.

Reviewer instructions:

- Read `.agents/skills/scp-skill-review/SKILL.md` first and enforce its C1–C6 semantics.
- Read SCP DNA and all 13 `.agents/skills/*/SKILL.md` files.
- Read `.agents/skills/evals/skill_pack_cases.json` and `tools/verify_scp_skills_pack.py`.
- Check that the declared inventory is exactly the actual inventory on the source SHA.
- Check C1 discovery/trigger quality, C2 scope separation, C3 context/progressive-disclosure constraints, C4 behavioral-eval coverage, C5 independence/calibration semantics, and C6 provenance/maintenance requirements.
- Inspect all 39 behavioral cases (three per Skill) for false positives, trivial assertions, contradictory expectations, or missing safety semantics.
- Do not treat static corpus presence as behavioral PASS.
- Do not transfer evidence from another SHA.
- Do not accept `PASS`, `VERIFIED`, or zero blockers unless the evidence supports it.
- Report defects with file/line references where possible.

Required reviewer verdict format:

```
Reviewer: <identity/service/model if known>
Source SHA: c8710387522cb9d43fbf746461e8cc51bc56a71f
C1: ...
C2: ...
C3: ...
C4: ...
C5: ...
C6: ...
Blockers: <integer>
Verdict: VERIFIED | INSUFFICIENT | CONTRADICTED | UNKNOWN
Notes: ...
```

This file is only a review request artifact and must not itself be treated as evidence that C5 passed.
