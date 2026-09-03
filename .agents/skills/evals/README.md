# SCP Skills C1–C6 verification harness

This directory contains pack-wide evaluation inputs. `skill_pack_cases.json` defines 39 behavioral cases: three per each of the 13 SCP skills.

Evidence semantics are deliberately strict:

- `tools/verify_scp_skills_pack.py` proves only deterministic/static portions of C1/C2/C3/C6 and that C4 corpus coverage exists.
- C4 becomes behavioral evidence only after a skill-enabled agent produces observed outputs for the cases on an exact source SHA.
- C5 requires an independent verifier from a different model/provider lineage. Self-report by the generator is not accepted.
- A final `VERIFIED` manifest must record source SHA, generator identity, verifier identity/model, timestamps, per-case observations, and blockers=0.

Never transfer a verdict from one SHA to another.
