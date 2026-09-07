# SCP Capability Security Review (Local copy)
Source: .agents/skills/scp-capability-security-review/SKILL.md

Core Methodology:
Review capability security, policy enforcement, sandbox, egress, filesystem scope, secret handling and approval.
Least privilege model: capability_id, subject = task_id + attempt_id, single tool or narrow group, specific resource, operation, expiry, revocation epoch, policy hash.
Validate tokens at issuance, invocation, and commit.
Deny-by-default (fail-closed).
Reject forgeries, tampered signatures, elevated scopes.
