---
name: scp-ga
description: Bootstrap and route work on the GA-LAB/SCP project using the live GitHub main branch as authority. Use whenever the user asks to analyze, design, code, debug, audit, verify, release, optimize, recover, or maintain SCP/GA-LAB.
---

# SCP / GA-LAB Bootstrap Skill

## Authority

For every SCP/GA-LAB task, treat `checken1994/GA-LAB` `main` as the live source authority. Before substantive work:

1. Read the current `main` SHA.
2. Read `.agents/skills/scp-dna/SKILL.md` and `.agents/skills/scp-dna/references/dna-principles.md` from that SHA.
3. Read `.agents/skills/README.md` and select the narrowest applicable SCP Skill(s).
4. Read each selected Skill from the same SHA before acting.
5. Never transfer PASS, CI, audit, or verification evidence from another SHA.

If GitHub is unavailable or the exact source cannot be read, say evidence is unavailable and do not invent repo state.

## Skill router

Route by task intent:

- Evidence-first reasoning, missing pieces, self-correction, claim verification → `scp-dna`.
- Capability/tool permissions, sandbox, egress, secrets, approvals → `scp-capability-security-review`.
- Browser/tool failure after possible side effect, reconciliation/recovery → `scp-computer-use-recovery`.
- LLM provider routing, circuit breakers, fallback, rate limits → `scp-gateway-resilience`.
- Learning loop, scraper, knowledge poisoning, autofix evolution → `scp-learning-loop-guard`.
- Static/integration/end-to-end/recovery truth classification → `scp-reality-verifier`.
- RC/release/freeze SHA/manifest/customer handoff → `scp-release-evidence-gate`.
- Process/port/health/readiness/runtime proof → `scp-runtime-audit`.
- Latency optimization without weakening controls → `scp-safe-latency-optimizer`.
- Audit or modify the Skills pack itself → `scp-skill-review`.
- Startup/environment/readiness troubleshooting → `scp-startup-troubleshooter`.
- Durable task state, attempt identity, leases, idempotency, restart recovery → `scp-task-kernel-review`.
- Browser DOM/CDP/orchestration/honeypot/prompt-injection safety → `scp-web-orchestration-safety`.

Use more than one Skill only when the task genuinely crosses their scopes. Start with `scp-dna` for material SCP decisions.

## Non-negotiable evidence semantics

- `PASS != TRUE`; PASS only means no failure was detected within the observed scope.
- Reality outranks reports, model confidence, consensus, and stale documentation.
- Missing evidence is not evidence of success or failure; classify uncertainty explicitly.
- Acceptance/golden fixtures do not substitute for missing production implementation.
- Do not elevate contract/test binding to runtime/evidence verification without the required observation.
- External or destructive writes require the applicable capability/policy/approval semantics.
- Fix the product where a valid test exposes a defect; do not weaken, delete, skip, or xfail the test to manufacture green.

## Completion discipline

A task may be called complete only within an explicit scope and on an exact SHA. For release-style claims, require the gates defined by the live release-evidence Skill and blocker count zero. After a source change, old verification is stale until rerun on the new SHA.

## Staleness protection

This installed Skill is a bootstrap/router, not the canonical copy of SCP DNA or the 13 domain Skills. If this file disagrees with live `main`, follow live `main`, report the discrepancy, and update/rebuild this bootstrap package.
