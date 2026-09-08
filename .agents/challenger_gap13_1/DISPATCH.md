# DISPATCH — Challenger GAP-13 #1 (Adversarial Cryptographic & Concurrency Attacks)

## 🔒 Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## PRE-SESSION MANDATE
You MUST call `view_file` on:
1. `c:\Users\check\Downloads\scp\GA.md`
2. `c:\Users\check\Downloads\scp\.agents\GEMINI.md`
3. `c:\Users\check\Downloads\scp\.agents\AGENTS.md`
4. `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`
5. `c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md`

## Mission & Scope
Read:
- `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md`
- `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`
- `c:\Users\check\Downloads\scp\.agents\worker_gap13_1\handoff.md`

Your role: Adversarial verifier. You MUST attack the new `commit_approval()` gate and transition guards.
Execute an adversarial test script targeting:
1. Cryptographic token manipulation:
   - Bit-flip attacks on HMAC signatures (both compact token string and CapabilityToken dataclass).
   - Prefix/suffix truncation on signature strings.
   - Injection of None/null/boolean/integer/malformed payloads.
   - Forged operator signatures with varied actor strings and timestamp alterations (future timestamps, expired timestamps).
   - Replay of valid approval tokens across different tasks (cross-task token replay attack).
2. Concurrency stress:
   - OCC race condition: concurrent threads attempting to call `commit_approval()` on the same task at the same version. Only 1 must succeed; the other must receive `OptimisticLockError`.
3. Verify that under all attack conditions, the task NEVER transitions to `READY` without valid, fresh, matching credentials, and DB state is consistent.
4. Output your adversarial findings and explicit verdict (`CONFIRMED_CORRECT` / `VULNERABILITY_FOUND`) to `c:\Users\check\Downloads\scp\.agents\challenger_gap13_1\handoff.md` and report back via `send_message`.
