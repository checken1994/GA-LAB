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

## Currently pending (20 tracked files; 3 target groups)

Inventory checked on 2026-08-26 found **20 pending candidate files**. They are
not 20 approved fixes: none has been independently reviewed, applied, or
rejected by this audit. Several entries have identical content hashes because
the same suggestion was queued more than once; those duplicates are retained
as review history rather than silently discarded.

- **16 `ai_patterns_pending_*.py` files** — target `scp/ai_patterns.py`.
- **2 `api_server_pending_*.py` files** — target `scp/api_server.py`; one
  older entry records a historical snapshot path in its header.
- **2 `conflict_resolver_pending_*.py` files** — target
  `scp/core/conflict_resolver.py`.

Review each file against the current target before taking any action. A
pending candidate is not evidence that the target is broken, and it must not
be auto-promoted to production or Gold data. Use the approve/reject/defer
procedure above and record the decision in the audit trail.

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
