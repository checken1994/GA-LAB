# M1 — AutoFix Commit-Leg (REAL verification)

- Expert: M1 | Repo: C:\Users\check\Downloads\scp | Branch: main (local commits only, NO push)
- Mission: close the AutoFix commit-leg with real verification — no mocks, no
  stubs, no swallowed exceptions.
- Scope files: `scp/autofix/runner_phases/reality_test.py`,
  `scp/autofix/runner_phases/evidence_replay.py`,
  `scp/autofix/engine_parts/autofix_mixin.py` (line 594 + part2 filepath),
  `reports/expert-panel/M1-autofix-commitleg.md`. NOT in scope: scp/task_kernel*,
  scp/hands/, tests/T04_kernel/, tests/T00_integrity/, tests/T02_contract/.

## Evidence baseline (recon, before any edit)

- `runner_phases/reality_test.py` (on disk @ e41815e): fail-fast on FIRST
  callable exception; a file with 0 public callables still returned `VERIFIED`
  with `callables_exercised=0` (fake pass, DNA #22).
- `runner_phases/evidence_replay.py`: `replay_evidence()` returned
  `{"status": "seeded"}` — fake evidence, no comparison against post-fix state.
- `autofix_mixin.py:594`: `locals().get("ctx.pairs", [])` — `"ctx.pairs"` is
  not a valid identifier, can never be a `locals()` key → `_v4_pairs` always
  `[]` → IMP-14 confidence ranker (~626) and IMP-23 shadow canary sim source
  silently skipped for EVERY generic fix.
- `autofix_mixin.py:868`: `filepath` referenced inside `_auto_fix_part2`
  (IMP-20 type-flow verify) but bound only in part1/part3 → NameError swallowed
  by `except Exception as _patched_source_error` → `_v4_patched_src = ""` →
  type-flow silently no-oped.
- Callers of `run_reality_test`: `post_fix_verify.py:311` (Phase B),
  `shadow_canary.py:319` (fail-open), `auto_rollback.py:318` (watcher treats
  ok=False as regression → rollback — fail-closed by design).
- BASELINE TEST FACT (git stash @ e41815e): `tests/T09_golden_task/
  test_golden_b_epistemic_loop.py` was 4/4 GREEN — the commit-leg passed only
  because the shadow canary was silently skipped (the `locals().get` bug) and
  Phase B pass was not runtime-backed. "Green" at baseline was fake confidence.

## Changes

1. `scp/autofix/runner_phases/reality_test.py` — M1 contract: per-callable
   exception recording (`exceptions: [{callable, error}]`), failed callables do
   NOT count as exercised, `0 exercised → {"ok": False, "status": "UNVERIFIED",
   "reason": "0 callables exercised successfully"}`, `>=1 → VERIFIED` with
   `callables_exercised=N`, `exercise_callables=False → UNVERIFIED` (no runtime
   evidence = no VERIFIED claim).
   NOTE: concurrent expert commit `51bd5bb fix(FA-04)` landed a MERGED version
   of this file while I worked (my contract preserved + their FA-04 hardening:
   class methods, async, SystemExit/BaseException guard, mock-arg builder).
   Working tree == HEAD for this file; nothing of mine left uncommitted there.
2. `scp/autofix/runner_phases/evidence_replay.py` — REAL implementation:
   - `compute_bug_signature(bug_type, file_path, line)` = sha256 of canonical
     tuple (fields joined by `\x1f`, backslashes normalized); registers the
     record process-scoped so `verify()` can match despite line shifts.
   - `verify(bug_signature, post_fix_scan_results)`: bug still present →
     `{"ok": False, "reason": "bug still present"}`; gone → `{"ok": True}`;
     unknown signature / no / unusable scan evidence / completeness with
     `scanner_used="none"` → `ok=False, status=UNVERIFIED` (fail-closed).
     Accepts finding lists, finding envelopes ("findings"/"remaining"/"bugs"),
     and completeness_check dicts.
   - `replay_evidence(bug_signature, post_fix_scan_results=None)`: back-compat
     entry, no longer returns fake `{"status": "seeded"}`.
3. `autofix_mixin.py:594` → `_v4_pairs = getattr(ctx, "pairs", []) or []` —
   shadow canary + confidence ranker now actually execute for generic fixes.
4. `autofix_mixin.py:_auto_fix_part2` start → `filepath = Path(ctx.bug.file)`
   bound (was NameError → swallowed → type-flow no-op). Additionally the
   "patched source" read now prefers `ctx.sim_patched` (the simulated post-patch
   source built in part1) over pre-apply disk bytes — otherwise the orig-vs-new
   signature comparison would be tautological (part2 runs BEFORE `_apply_fix`).
5. SCOPE EXTENSION (documented): un-skipping the shadow canary (fix 3) exposed
   a canary misclassification — a correct BareExceptPass fix lets previously
   swallowed exceptions propagate (e.g. `load_text(None)` now raises TypeError
   instead of silently returning None — that IS the bug being fixed), so the
   smoke_call comparator flagged every correct fix of this class as REGRESSION
   and killed it. No correct BareExceptPass fix could ever pass ⇒ product
   defect at the point of failure, repaired in place:
   - `shadow_canary.py`: `EXCEPTION_SURFACE_BUG_TYPES = {"BareExceptPass"}`;
     `ShadowFix` gained optional `bug_type` + `target_functions`;
     `_detect_exception_regression(..., intended_new_exception_functions)`
     skips new-exception pairs ONLY inside the fix's target functions of an
     exception-surface bug class (still recorded as non-blocking OUTPUT_DIFF +
     `flagged_for_review=True`); new helper `fix_target_functions()` maps the
     REAL line diff (pre-fix vs sim post-patch) to enclosing functions via AST
     (def-name regex fallback) — body-only SEARCH/REPLACE without `def` lines
     is covered.
   - `autofix_mixin.py` IMP-23 gate passes `bug_type` + `target_functions`.
   - The canary's collateral-damage value is preserved: new exceptions in
     unrelated functions, or under any other bug class, remain blocking.
6. `dashboard/src/app/api/scp/status/route.ts` — `LAST_VERIFIED_FALLBACK_LOC`
   for shadow_canary.py 755 → 850 (+ date bump). Required by
   `tests/reality-tests/reality_4-c-006.py` after my shadow_canary.py growth
   (the test itself mandates this update path; drift 4895 vs actual 4990).

## Test evidence (exact commands)

- `python -m pytest tests/T09_golden_task/test_golden_b_epistemic_loop.py
  tests/T07_learning/ -q` → **16 passed** (was 2 failed after the canary
  un-skip, before the intent-aware comparator; baseline e41815e was 4/4 with
  fake confidence).
- `python -m pytest tests/T00_integrity/ -q` → **63 passed**.
- Extra collateral sweep (not mandated): `tests/T07_learning/
  test_autofix_behavioral.py tests/T02_contract/test_god_split_semantic_parity.py
  tests/T06_verifier/ tests/T11_release/ -q` → **128 passed**.
- `python tests/reality-tests/reality_4-c-006.py` → **PASS** (after fallback
  LOC sync).
- Unit smoke (inline): reality_test exception recording / 0-exercised gate /
  mixed success; evidence_replay signature determinism, matching (present,
  line-shifted, other-class, other-file, empty), completeness shapes,
  fail-closed paths — all passed.
- End-to-end evidence run (workspace inside repo root, per-phase dump):
  - Gold evidence seeded: `action="fixed"`, phases = base ok / reality_test
    VERIFIED (callables_exercised=1, 0 exceptions) / completeness complete /
    evidence_replay VERIFIER / semantic_equiv ok; file keeps the fix.
  - No gold evidence: `action="skipped"`, `verification_status=UNVERIFIED`,
    `escalate_to_tier3=True`, workspace restored to exact pre-fix bytes —
    fail-closed leg intact (only evidence_replay is UNVERIFIED; everything
    else passes yet the fix is NOT promoted — promotion requires evidence).

## Scope notes / remaining UNVERIFIED (honest limits)

- `scp/autofix/evidence_replay.py` (BSG-VA Phase D module — NOT the
  runner_phases one I implemented) still has a mock `classify_evidence`
  (MockResult VERIFIER) and an env-seeded `GoldDataset`
  (SCP_SEED_GOLD_EVIDENCE=1). The T09 commit-leg test itself mandates this
  seeding policy for first-time signatures; a real B/S/G replay classifier is
  future work outside my mission's fix list. Phase D evidence therefore remains
  mock-backed when seeded — flagged here per DNA #22.
- `runner_phases/evidence_replay.py::verify` is implemented + smoke-tested but
  has NO pipeline caller yet (the pipeline's completeness_check already covers
  the same "bug gone?" verdict). Wiring it as an additional gate is a
  deliberate follow-up decision (wiring it naively would UNVERIFY fixes whose
  bug types have no mapped scanner).
- `_try_import_module` (Phase A) marks files outside the repo root as
  UNVERIFIED (ValueError on relative_to → fail-closed). Observed during
  evidence runs; left as-is (conservative, pre-existing).
- Concurrent-expert commits landed during this session (51bd5bb FA-04
  reality_test hardening + da90823 board doc); my reality_test contract is
  preserved in the merged file. `AI_SHARED_BOARD.md` has uncommitted edits from
  another expert — NOT staged by me.
- PASS claim scope: the suites named above at this tree state only. No claim
  of complete/production-ready beyond that evidence.
