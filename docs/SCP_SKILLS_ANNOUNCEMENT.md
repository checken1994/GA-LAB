# SCP Skills: Evidence-First Safety for AI-Agent Runtimes

> **Community introduction and request for independent review**

## Why this exists

AI agents can write code, call tools, browse websites, and change files. The difficult question is not only whether an agent can produce a plausible answer. The difficult questions are:

- What is the agent allowed to do for this specific task and resource?
- What actually happened after a tool timed out?
- Did a side effect happen even though the response was lost?
- What evidence is strong enough to mark a task complete?
- Can an old worker, revoked capability, or unsafe retry act again?

**SCP Skills** is a small open skill pack for making those questions explicit. It is intended for engineers and agent builders who want a repeatable way to reason about boundaries, evidence, recovery, and release readiness.

## The nine skills

| Skill | What it covers |
|---|---|
| [`scp-dna`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-dna/SKILL.md) | Evidence-first reasoning, missing-piece detection, and self-audit |
| [`scp-capability-security-review`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-capability-security-review/SKILL.md) | Task-scoped capabilities, resource boundaries, approval, egress, and secret safety |
| [`scp-computer-use-recovery`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-computer-use-recovery/SKILL.md) | Safe recovery when a browser or tool may have already caused a side effect |
| [`scp-reality-verifier`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-reality-verifier/SKILL.md) | Separating static, integration, end-to-end, and recovery evidence |
| [`scp-release-evidence-gate`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-release-evidence-gate/SKILL.md) | Reproducible release, runtime, security, chaos, and rollback gates |
| [`scp-runtime-audit`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-runtime-audit/SKILL.md) | Live process, port, health, readiness, and runtime evidence checks |
| [`scp-safe-latency-optimizer`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-safe-latency-optimizer/SKILL.md) | Reducing latency without bypassing policy, verifier, revocation, or approval |
| [`scp-startup-troubleshooter`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-startup-troubleshooter/SKILL.md) | Evidence-led diagnosis of launcher, dependency, port, and readiness failures |
| [`scp-task-kernel-review`](https://github.com/checken1994/GA-LAB/blob/main/skills/scp-task-kernel-review/SKILL.md) | Durable task identity, state, journal, lease, checkpoint, idempotency, and kill switch |

The complete directory is available at [`skills/`](https://github.com/checken1994/GA-LAB/tree/main/skills), with a practical overview in [`skills/README.md`](https://github.com/checken1994/GA-LAB/blob/main/skills/README.md).

## The central rule

> A skill is a workflow contract, not a permission grant.

An agent should not receive more authority simply because a model asks for it. External writes, uploads, deletes, payments, credential changes, publishing, and privilege changes require a task-scoped capability, an explicit policy decision, the necessary approval, an independent postcondition, and an audit trail.

When the state is unclear, the safe answer is not a blind retry. The workflow should move to `UNKNOWN`, `RECONCILING`, `HUMAN_REVIEW`, or `BLOCKED` until the actual state is understood.

## Four evidence levels

| Level | Meaning |
|---|---|
| **Static** | A file, route, schema, or assertion exists. This does not prove runtime behavior. |
| **Integration** | Components connect and a bounded interaction works. |
| **End-to-end** | A real task crosses planning, policy, tool, observation, verification, audit, and artifact boundaries. |
| **Recovery** | End-to-end evidence plus crash, timeout, lease, unknown-state, or restart handling. |

A green test is reported as `PASS_WITHIN_SCOPE`. It must not silently become “no bugs”, “production safe”, or “top-ranked”. Evidence must remain tied to a commit, test profile, workload, and time.

## A simple lost-response example

```text
Action dispatched
      ↓
Client timeout
      ↓
Agent does not know whether the action happened
      ↓
Reconcile the real external state
      ↓
Retry only if safe; otherwise UNKNOWN or human review
```

This is deliberately conservative. A timeout means that the client did not receive a result. It does **not** prove that the external action did not happen.

## How to try the pack

The documents are plain Markdown. Copy the directories into the skill location used by your agent, or read the relevant `SKILL.md` directly from the repository. For the full pack, preserve the `references/dna-principles.md` file used by `scp-dna`.

```bash
git clone https://github.com/checken1994/GA-LAB.git
cd GA-LAB
ls skills/*/SKILL.md
```

Start with `scp-dna` when a claim or proposed fix is unclear. Add `scp-capability-security-review` before granting a tool capability. Use `scp-computer-use-recovery` when a tool may have crossed a side-effect boundary. Finish with `scp-reality-verifier`, `scp-runtime-audit`, and `scp-release-evidence-gate` when the question is whether the result is actually proven.

## What this is — and what it is not

SCP Skills is a reusable engineering and review layer. It is **not** an AI model, a hosted service, an operating-system sandbox, a secret broker, or a security certification. The surrounding SCP repository contains an experimental runtime implementation; its current status is intentionally reported as `CANDIDATE_NOT_PROVEN`.

This project does not claim uninterrupted 24/7 operation, complete security, OS-level isolation, official Ragas/ARES success on 1,000 RAG questions, or superiority over every other agent framework. Those claims require independent, workload-specific evidence.

## What feedback would help

Community review is welcome. The most useful feedback is concrete: identify an ambiguous rule, show a missing failure mode, propose a focused test, or demonstrate that a recommendation is unsafe under a specific task/resource/attempt combination. Please include the relevant skill, a minimal reproducible example, expected behavior, observed behavior, and the evidence profile used.

Open a GitHub Issue or Pull Request in the [GA-LAB repository](https://github.com/checken1994/GA-LAB). Do not include tokens, cookies, passwords, private logs, personal data, or live exploit payloads.

## Tiếng Việt

**SCP Skills** là bộ 9 skill mã nguồn mở giúp xây dựng và kiểm tra runtime cho AI agent theo hướng evidence-first. Bộ skill tập trung vào quyền theo từng task/resource, recovery khi mất response, kiểm tra postcondition, audit runtime, release gate, lease, checkpoint, idempotency và kill switch.

Đây là bộ workflow hướng dẫn, không phải model AI hay giấy chứng nhận an toàn. `PASS_WITHIN_SCOPE` chỉ có nghĩa là chưa thấy lỗi trong phạm vi kiểm tra hiện tại. Khi chưa biết trạng thái thật, SCP ưu tiên `UNKNOWN`, `RECONCILING` hoặc `HUMAN_REVIEW`, không retry mù.

## License

MIT for this repository. Third-party tools, models, and dependencies may have separate licenses.
