# SCP DNA — Security Policy

## Reporting a vulnerability

Please do not publish credentials, exploit steps, customer data, or an actively exploitable vulnerability in a public issue.

Report security issues privately to:

```text
checken1994@gmail.com
```

Before publication, confirm that this address is controlled by the project owner and monitored for security reports.

Include, where safe to share:

- Affected version or commit.
- Component and configuration.
- Reproduction steps or a minimal proof of concept.
- Impact assessment.
- Suggested mitigation.
- Whether the issue is already public or actively exploited.

Do not include real passwords, API keys, private tokens, personal data, or customer information. Redact them before sending.

## Response process

The maintainers will attempt to:

1. Acknowledge receipt.
2. Confirm the affected component and version.
3. Reproduce or validate the report.
4. Coordinate a fix and disclosure timeline.
5. Credit the reporter where the reporter agrees.

This document is a project process, not a guarantee of response time, warranty, or liability.

## Release hygiene

Before every public release, run secret scanning, dependency/license scanning, and a review of generated artifacts. Rotate any credential that has appeared in a repository, log, issue, screenshot, build artifact, or chat.
