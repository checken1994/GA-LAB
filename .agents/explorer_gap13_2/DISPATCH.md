# DISPATCH — Explorer GAP-13 #2 (CapabilityToken & Cryptographic Verification)

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
Read `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` and `c:\Users\check\Downloads\scp\.agents\orchestrator_10\SCOPE.md`.
Your role: Read-only exploration agent. Do NOT modify source code files.
Investigate `scp/core/capability_token.py` and cryptographic verification mechanisms:
1. Examine `CapabilityToken` dataclass, HMAC-SHA256 signing (`issue()`), signature validation (`validate()`), secret handling (`SCP_CAPABILITY_SECRET`), and permissions structure.
2. How is `approval:grant` capability represented in `CapabilityToken` (e.g. `capabilities` list/set or actions)?
3. How should `TaskKernel` authenticate the approval token?
   - Support `CapabilityToken` instance or serialized token string with valid signature.
   - Verification must fail closed: missing signature, invalid signature, expired token, mismatched task/scope, missing `approval:grant` permission must raise explicit authentication/authorization errors (`InvalidTokenSignatureError` / `UnauthorizedApprovalError` or `InvalidTransition`).
   - What about operator signature? Is there an operator signature convention in the codebase (e.g. ED25519/HMAC or authorized operator public key/secret)?
   - Ensure FA-05 (NO self-granting authority): TaskKernel does NOT generate the token; external authority/operator must provide it.
4. Output report to `c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md`.

## 2026-09-08T02:07:22Z
User Request received:
Investigate CapabilityToken and cryptographic verification in scp/core/capability_token.py and related modules. Analyze HMAC-SHA256 signing, validation, secret management (SCP_CAPABILITY_SECRET), permission structure (approval:grant capability), operator signatures, and fail-closed error handling. Design how TaskKernel can securely verify approval tokens without self-granting authority (FA-05).
Output comprehensive findings to c:\Users\check\Downloads\scp\.agents\explorer_gap13_2\handoff.md and report back via send_message.
