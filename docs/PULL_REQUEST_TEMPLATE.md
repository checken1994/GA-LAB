# PR: <one-line summary>

> **Phase 2 rule (Root Cause 2 fix):** Every PR that changes code MUST
> include a reality-test script that demonstrates the bug BEFORE the fix
> and demonstrates the fix works AFTER. This is the enforcement for
> SCP-DNA #2 (vòng lặp khép kín — "fix" without reality test creates new
> bugs), #22 (PASS≠TRUE), and #26 (reality test). PRs without a passing
> reality-test will be blocked by `tests/run-reality-tests.sh`.

## Finding ID(s) addressed
<!-- e.g., 4-b-002, 4-a-004, 4-d-004. Reference worklog finding IDs. -->

## Root cause analysis (DNA #1 — Hỏi Tại sao)
<!-- 3-5 whys leading to the ROOT cause, not the symptom. -->
1. Why does the bug exist? ...
2. Why wasn't it caught? ...
3. Why did prior fix (if any) create this bug? ...
4. ...
5. ROOT: ...

## Fix description
<!-- What changed, where, and why this approach. Must be small + reversible
     (DNA #7 no harm, #17 hành động khi chưa biết hết). -->

## Reality test (DNA #2, #26 — MANDATORY)
- **Script path:** `tests/reality-tests/reality_<finding-id>.py` (or `.sh`)
- **Before fix:** script fails (demonstrates bug exists)
- **After fix:** script passes (demonstrates fix works)
- **Result:** paste the `✓ Reality test <id> PASSED (N/N assertions)` output here

<!-- If you cannot write a reality-test (e.g., requires running services),
     explain why and what manual verification was done. DNA #23: honest limit.
     A PR with "skipped reality-test" must justify the skip — silence is not
     acceptable. -->

## Rollback plan (DNA #7, #9)
<!-- How to revert if the fix causes a regression. Single command preferred. -->
`git revert <commit>` or `git checkout <prev> -- <file>`

## Open questions (DNA #23, #25)
<!-- What still cannot be verified with current capability? What might this
     fix break? What new observation gap does it create? -->

## Checklist
- [ ] Root cause identified (not just symptom)
- [ ] Fix is small + reversible (single commit preferred)
- [ ] Reality-test script written and passing
- [ ] Reality-test would FAIL before the fix (proves it tests the right thing)
- [ ] No new DNA #22 violation introduced (no claim without enforcement)
- [ ] Rollback plan documented
- [ ] `tests/run-reality-tests.sh` passes locally (CI gate)
