# SCP DNA — Read-Only Secret Scan Report

## Scope

Scan date: 2026-08-17

Target: `C:\Users\check\Downloads\scp`

Mode: read-only. No file was modified, no process was stopped, and no secret value was printed or copied.

## Findings

### Sensitive filenames

The working tree contains:

```text
.env
.env.test
.env.test.bak-bridge-20260817
```

These files are ignored by `.gitignore` and `.env` is not tracked by the current Git index. They still contain configuration that must not be included in a public release. The existence of `.env.test.bak-bridge-20260817` means backup files also need to remain excluded.

### High-confidence patterns

The read-only scan did not find a confirmed private-key marker, GitHub token prefix, AWS access-key prefix, or obvious long-form provider key in the current tracked working tree under the high-confidence patterns used.

The scan did find many **references** to names such as `OPENAI_API_KEY` and `OPENROUTER_API_KEY` in code, tests, documentation, and startup scripts. These are mostly variable names, environment lookups, placeholders, or examples; a pattern match is not proof that a live secret is present.

### Git history

High-confidence pattern matches were associated with commits and files including documentation, startup scripts, the LLM bridge, and scanner code. The scan did not confirm a literal private key or recognized token value from the restricted output. Because history matches require a final independent review before publication, do not treat this report as a legal or cryptographic guarantee that the history is clean.

## Risk rating

| Area | Result | Risk |
|---|---|---|
| `.env` tracked | Not tracked; ignored | Medium until release archive is checked |
| `.env.test` / backup tracked | Ignored; not reported as tracked | Medium until release archive is checked |
| Private key marker | No confirmed match in restricted scan | Low/unknown; run a second scanner before public release |
| GitHub token pattern | No confirmed match in restricted scan | Low/unknown |
| Provider key pattern | Variable references found; no confirmed literal value | Medium; review release files and history |
| Secret history cleanliness | Not proven | High until an independent scanner/review passes |

## Required actions before public release

1. Revoke and rotate any credential that has ever appeared in a file, log, screenshot, issue, chat, or Git commit.
2. Confirm `.env`, `.env.*`, `.private-secrets/`, backups, logs, browser profiles, and generated artifacts are excluded from the release archive.
3. Run an independent secret scanner over the full Git history, such as Gitleaks or TruffleHog, and review findings without publishing secret values.
4. Inspect the exact release tag/archive, not only the working tree.
5. Do not publish while any finding is unresolved or marked `UNKNOWN`.

## Scope limitation

This report is a defensive pre-publication scan, not proof that no secret exists. It used filename checks, Git index/history checks, and restricted high-confidence patterns. Secrets can be encoded, split, encrypted, embedded in binaries, stored in Git LFS, or hidden under unusual names.
