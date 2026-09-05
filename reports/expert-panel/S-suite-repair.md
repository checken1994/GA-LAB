# S-suite-repair — Progress Log

Panel role: SUITE-REPAIR EXPERT. Branch: main, HEAD `1d9724a`. Full write authority, local commit only (no push).

## Baseline (verified)

- Full suite: 2 failed / 427 passed / 1 skipped / 3 errors.
- Mission-listed failures:
  - `tests/T05_gateway/test_provider_timeout_recovery.py::test_openrouter_timeout_recovers_via_task_free_fallback` (FAILED + teardown ERROR)
  - `tests/T05_gateway/test_provider_failover.py::test_breaker_open_skips_dead_provider_without_network_call` (teardown ERROR)
  - `tests/T05_gateway/test_provider_failover.py::test_all_providers_down_fails_closed` (teardown ERROR)
  - `tests/T11_release/test_rc_workflow_runtime_contract.py::test_acceptance_fixture_seeds_isolated_distinct_family_pricing_proofs` (FAILED per mission baseline)

## Diagnosis evidence

### T05 trio — root cause (deterministic, 3/3 runs)

The untracked `tests/T05_gateway/conftest.py` (parallel workstream) installs:

1. autouse `isolated_gateway_state`: free-only env (`SCP_LLM_COST_MODE=free_only`, proof DB in tmp), and a **fail-closed httpx monkeypatch** — any `httpx.Client/AsyncClient.send` raises and is recorded; teardown asserts zero HTTP attempts.
2. `pricing_runtime` fixture: seeds fresh immutable `PricingProof` rows (via `PricingProofStore.record` + `GovernedEvidenceWriter` evidence) into the isolated proof DB.

The zero-cost commit `8370e6f` ("migrate provider routing to verified-free candidates only") installed Z3 (`install_free_only_provider_router`) on `OpenRouterProvider.chat` at package import (`scp/llm_gateway/__init__.py:20`). Z3 authorizes ALL candidates at the PEP BEFORE dispatch (`zero_cost_runtime.py:196-211`); `authorize_outbound` performs exactly one bounded catalog refresh for `DENY_UNKNOWN_PRICE`/`DENY_STALE_PRICE` (`zero_cost_runtime.py:104-117`).

The three failing tests were written pre-Z3 (paid-primary semantics) and seed no proofs:

- every candidate → `DENY_UNKNOWN_PRICE` → product triggers the by-design catalog refresh → `free_catalog._fetch_catalog_models` swallows the conftest's sentinel error (`free_catalog.py:54`) → teardown `assert unexpected_http == []` fires with 3 recorded sync attempts (`conftest.py:79`).
- `test_openrouter_timeout_recovers_via_task_free_fallback` additionally FAILED in-body: Z3 blocked all candidates pre-dispatch, so the fake `_call_model` recorded zero calls (`calls == []`).

Classification: **HARNESS_BROKEN** (tests encode superseded paid-primary semantics; product behavior is correct fail-closed free-only). Fix = rewrite tests to verified-free-only semantics with seeded proofs; assertions kept and raised (exact dispatch lists, `waiting_free_quota`/`blocked_zero_cost_proof` labels, paid-never-dispatched proofs from the Z2 outbound-event audit). No assertion weakened; no skip/xfail; conftest fail-closed HTTP property preserved.

### T09 golden-B flake (observed 1/3 runs, outside the 5 listed — root-caused anyway)

`test_golden_b_verified_fix_commits_to_durable_state` failed once with
`'reason': 'WHY-GATE blocked: FALSIFICATION: The patch still leaves a gap by only catching `OSError`...'`
—an LLM-shaped verdict. Chain: `scp/autofix/runner.py:57-88` loads the repo `.env` at import time; `.env` contains `SCP_WHY_LLM_ENABLED=1` (plus real keys, `SCP_EGRESS_MODE=allowlist`) → WHY-GATE LLM layer on → `_call_why_provider` → real gateway `chat_sync(task="why")` → real network dispatch (evidence: `data/foundation/zero_cost.sqlite` mtime advanced during suite runs; 4 MB WAL) → probabilistic verdict flips the test. The sibling test `test_golden_b_security_weakening_patch_is_killed_by_policy_gate` already pins `SCP_WHY_LLM_ENABLED=0`; the verified-fix leg does not. Harness fix: pin the same deterministic env in the verified-fix leg (strictness preserved — deterministic falsification patterns still gate).

### T11 acceptance-fixture test — NOT reproducible on current HEAD

Passed in isolated run, in `tests/T05_gateway tests/T11_release` run, and in 2 full-suite runs (4 total). Note: full-suite run 1 showed `tests/T09_golden_task/test_golden_b_epistemic_loop.py::test_golden_b_verified_fix_commits_to_durable_state` failed instead (2F/427P/1S/3E — same counts, different flake), run 2 was 1F/428P/1S/3E (only the deterministic T05 failure). T11-adjacent hygiene checked: `scripts/run_scp_acceptance.py` RuntimeHarness DOES seed isolated proofs (`scripts/run_scp_acceptance.py:188-225`); `SCP_MULTI_LLM_CROSSCHECK` is not set by `.env` or any product assignment.

## Fix log

1. `tests/T05_gateway/test_provider_timeout_recovery.py` — rewritten for Z3: seed fresh free proofs for `free_fallback` + `openrouter/free`, PAID proof for the primary (DENY_PAID without catalog refresh); assertions: exact dispatch order `[free_fallback, "openrouter/free"]`, recovered answer, provider label, paid primary never in `calls`.

2. `tests/T05_gateway/test_provider_failover.py` — `FakeClient` now records dispatched model names (strictness raised). Breaker test: seed proofs for all 3 chat candidates (`unverified-chat`, `openrouter/free` free; `unverified-primary` PAID), keep `answer is None` + `dead.calls == 0`, add `label == "none"`, add Z2 audit assertions (no `actual_sent=1` event; `DENY_PAID` event recorded for the paid primary). All-providers-down test: keep `(None, "none")` + `failures == 1`; add provider-level `waiting_free_quota` label, exact dispatched-model list `["unverified-chat", "openrouter/free"]`, paid never dispatched, and Z2 sent-event set equality.
3. `tests/T09_golden_task/test_golden_b_epistemic_loop.py::test_golden_b_verified_fix_commits_to_durable_state` — pin `SCP_WHY_LLM_ENABLED=0` (same pattern as the security-weakening leg at line 193) to remove the probabilistic LLM falsification layer from the golden contract; deterministic patterns remain authoritative.

Status: `python -m pytest tests/T05_gateway tests/T11_release -q` → **112 passed, 0 failed, 0 errors**.

4. Meta-audit fallout: `tests/T00_integrity/test_meta_audit.py::test_meta_audit_t05_no_forbidden_semantic_patterns` flags the literal bigram "paid primary" in T05 sources (guardrail against superseded semantics). Reworded 3 comments in my rewrites (assertions untouched).

## Verification (reality evidence)

- `python -m pytest tests/T00_integrity tests/T05_gateway tests/T11_release -q` → 166 passed.
- Full suite run A (post-fix): **434 passed / 1 skipped / 0 failed / 0 errors** (110.96s).
- Full suite run B (stability, post-fix): **434 passed / 1 skipped / 0 failed / 0 errors** (126.84s).
- Commands: `python -m pytest -q --no-header` from repo root; commit snapshot recorded below.

## Scope notes and residuals

- `tests/T05_gateway/conftest.py` was untracked (parallel workstream). My rewritten tests depend on its `pricing_runtime` fixture and the fail-closed httpx monkeypatch, so it is included in this commit — without it the T05 contract is not reproducible from a clean checkout.
- Residual (pre-existing, outside the 5 listed failures, NOT changed here): several non-T05 tests still hit the real network via `.env` auto-load (`runner.py` import-time `load_dotenv`) — evidence: `data/foundation/zero_cost.sqlite` WAL grows during suite runs. The T09 WHY-GATE pin removes the one observed nondeterministic consumer; a repo-wide hermeticity pass (e.g., conftest-level `SCP_EGRESS_MODE=deny` for contract tests) is a separate decision.
- T09 `test_golden_b_good_patch_is_apply_verified_then_failclosed` shares the same latent WHY-GATE-LLM hazard but accepts `skipped` outcomes, so it did not flake; left unpinned (smallest reversible patch).
- T11 `test_acceptance_fixture_seeds_isolated_distinct_family_pricing_proofs`: not reproducible on HEAD `1d9724a` (passed 4/4 runs incl. 2 full suites); no change made. The identified env-pollution mechanism (`.env` load at runner import) remains the plausible historical cause family.
- PASS scope: no failure observed in the stated runs on this machine; this is not a claim of complete/secure/production-ready.

## Commit

- `932cc32` `fixS(suite): repair T05 free-only failover contracts, pin deterministic WHY gate in golden-B, commit T05 fail-closed conftest` — local only, NOT pushed.
- Branch reality note: mission said "main", but the checkout's live branch is `fix/t09-golden-task-debt` (main is behind at c68559b; session-start HEAD 1d9724a lives only here). Expert B (`fixB(kernel)` 09461ba) committed on this same branch mid-session; the fixS commit sits on top of exactly the tree the baseline failures were verified against. Topology left untouched for panel reconciliation.
