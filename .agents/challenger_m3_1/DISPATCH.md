# Challenger 1 Dispatch: Adversarial Penetration (Token Forgery & Cryptographic Attacks)

- Working Directory: c:\Users\check\Downloads\scp\.agents\challenger_m3_1
- Authoritative User Request: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
- Project Scope: c:\Users\check\Downloads\scp\.agents\orchestrator_7\PROJECT.md
- Worker Handoff: c:\Users\check\Downloads\scp\.agents\worker_m3\handoff.md

## Scope of Penetration
- Execute adversarial penetration testing attempting:
  1. Forging tokens out of thin air without the secret.
  2. Forging tokens with old fallback secret (`b"dev-secret-do-not-use-in-prod-12345"`).
  3. Forging tokens with empty key, dummy key, or mismatched key.
  4. Bit-flipping and signature truncation attacks.
  5. Payload modification (e.g. elevating subject from `hands:pc.read` to `hands:pc.write_file` or modifying epoch).
  6. Submitting legacy tokens without signature.
- Verify that `CapabilityAuthority.validate()` strictly rejects 100% of forged/tampered tokens with `InvalidTokenSignatureError`.
- Formulate explicit verdict: APPROVE (all blocked) or REQUEST_CHANGES (vulnerability detected).
- Deliver report to `c:\Users\check\Downloads\scp\.agents\challenger_m3_1\handoff.md`.

## 2026-09-07T12:51:00Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Challenger 1 (teamwork_preview_challenger) for Milestone 3 (GAP-08 & Adversarial Penetration).
Your working directory is: c:\Users\check\Downloads\scp\.agents\challenger_m3_1
Your task assignment is at: c:\Users\check\Downloads\scp\.agents\challenger_m3_1\DISPATCH.md
Read the authoritative user request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Read project context at: c:\Users\check\Downloads\scp\.agents\orchestrator_7\PROJECT.md
Read worker handoff at: c:\Users\check\Downloads\scp\.agents\worker_m3\handoff.md
Read skill instructions at: c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md and c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md

Tasks:
- Execute adversarial penetration testing attempting token forgery:
  1. Forging tokens out of thin air without the secret.
  2. Forging tokens with old fallback secret (b"dev-secret-do-not-use-in-prod-12345").
  3. Forging tokens with empty key, dummy key, or mismatched key.
  4. Bit-flipping and signature truncation attacks.
  5. Payload modification (e.g. elevating subject from hands:pc.read to hands:pc.write_file or altering epoch).
  6. Submitting legacy tokens without signature.
- Verify CapabilityAuthority.validate() strictly rejects 100% of forged/tampered tokens with InvalidTokenSignatureError.
- Formulate explicit verdict: APPROVE (all blocked) or REQUEST_CHANGES.
- Deliver report to `c:\Users\check\Downloads\scp\.agents\challenger_m3_1\handoff.md` and notify parent via send_message.
