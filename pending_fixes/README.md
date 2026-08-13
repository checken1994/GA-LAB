# `pending_fixes/` — Tier-3 human-approval-required fix suggestions

This directory holds fix suggestions that SCP's autofix engine could NOT
safely auto-parse into a patch (Tier-3). Each file is a comment-only
Python stub that records:

- the original file path the fix applies to
- the LLM's suggested fix (in `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`
  diff format, or as free text)
- a safety classification (User Safety: safe / unknown / risky)

**No code in this directory is executed.** These are pending human review.

## Why this directory exists (SCP DNA #4 + #11)

SCP's autofix engine has three tiers:

- **Tier 1** — high-confidence, fully-auto-applied, rollback-protected.
- **Tier 2** — auto-applied but with extra reality-tests + cooldowns.
- **Tier 3** — *human-approval-required*. The LLM produced a suggestion,
  but the AST patcher could not safely apply it (ambiguous diff,
  context-dependent change, file too large, or the diff touches
  high-stakes logic). The suggestion is parked here as a `.py` stub
  for a human reviewer to read + decide.

DNA #4 (Con người quyết định — SCP tìm chỗ sai, con người quyết định) +
DNA #11 (Human-in-the-loop thật — con người có thực sự hiểu điều mình
đang phê duyệt không?) require this surface. Without it, Tier-3 fixes
silently rot — autofix's "human review" step is rubber-stamp-or-ignore,
which violates #11.

## How to review (operator runbook)

1. `ls pending_fixes/` — see what's waiting.
2. For each `<file>_pending_<ts>_<hash>.py` file:
   1. Open it. Read the `Original file:` line to know which source
      file the fix targets.
   2. Read the `Suggested fix from LLM:` block. If it's a
      `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` block, that's a
      diff against the current contents of `Original file:`.
   3. Open `Original file:` and locate the SEARCH block in the current
      source.
   4. **Decide**:
      - **Approve** — the fix is correct + safe. Apply it manually
        (replace the SEARCH block with the REPLACE block in the
        original file). Run the relevant reality-tests. Commit.
      - **Reject** — the fix is wrong / unnecessary / unsafe. Delete
        the pending_fixes file. Optionally log the rejection in
        `data/permission_requests.jsonl` for audit trail (DNA #8).
      - **Defer** — need more info. Leave the file in place; it will
        surface again on the next weekly reminder (see below).

## Currently pending (3 files)

- `api_server_pending_1786246424_40b6b9bc.py`
  - Target: `scp/api_server.py` (or the round-11 snapshot path listed
    in the file header).
  - Suggestion: address Ruff rule `PLW0603` (global statement use).
  - Note: the suggestion is a one-liner pointing at Ruff docs — review
    whether the `global` is genuinely needed or refactorable.

- `conflict_resolver_pending_1786246579_c72bdb3c.py`
  - Target: `scp/core/conflict_resolver.py`.
  - Suggestion: replace `pass # metric tracking is best-effort` with
    `logger.debug("Metric tracking is best-effort")` (slightly better
    observability — `pass` swallows silently, `logger.debug` records
    it under debug log level).

- `conflict_resolver_pending_1786246636_393402a1.py`
  - Target: `scp/core/conflict_resolver.py` (same file, different fix).
  - Suggestion: `User Safety: safe` marker only — review whether this
    is the same as the above or a different fix.

## Weekly reminder

Add to your calendar / cron / TODO list:

> Every Monday 09:00 — `ls pending_fixes/`. If non-empty, review each
> file (see runbook above). Target: zero pending files at end of week.

Operator-visible automation idea (not yet implemented): the dashboard's
"Closing section" should display `pending_fixes/` count + a "Review
now" link to this README. See `dashboard/src/components/dashboard/closing-section.tsx`
for where to add it (left as a follow-up — out of scope for Task Local-D).

## Audit trail

When you approve/reject a fix, record it in `data/permission_requests.jsonl`
with:

```json
{"ts": "2026-...", "decision": "approve"|"reject"|"defer",
 "pending_file": "<filename>", "target_file": "<original path>",
 "reviewer": "<operator name>", "note": "<optional one-liner>"}
```

This is required by DNA #8 (KB accumulation — every audit decision
logged with before/after hash, reality-test result, rollback token).
