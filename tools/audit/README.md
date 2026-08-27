# Audit helpers

This directory contains sanitized, read-only helpers used to inspect runtime metadata. They must not print secrets, cookies, tokens, raw private logs, prompts, or database rows.

Machine-specific probes and their sanitized outputs may be kept under `tools/audit/local/`. That path is intentionally ignored because those files belong to a particular workstation and are not release source or portable evidence.
