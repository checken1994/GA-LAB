# SCP Capability Security Review Skill (Local Copy)
Source: .agents/skills/scp-capability-security-review/SKILL.md

Core Methodology:
- Check capability by task + attempt + resource + action.
- Deny-by-default: without valid capability, tool/action is rejected immediately.
- PEP must sit immediately before execution drivers (subprocess, filesystem).
- Cryptographic capability token (HMAC-SHA256, active epoch, matching scope).
- Secret broker protection: no secrets leaked in logs or prompts.
