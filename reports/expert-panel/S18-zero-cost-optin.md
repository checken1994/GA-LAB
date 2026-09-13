# S18 — Zero-cost wall: compile-time mandate → opt-in deployment policy

- **Worker:** S18
- **Date:** 2026-09-13
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (branch not changed)
- **Owner directive (verbatim intent):** "tôi chỉ bảo dùng API free cho trường hợp của
  tôi, CHỨ KHÔNG phải mã hóa cứng bắt buộc SCP đòi API free — xóa cái này đi."
- **Skills bound (mandatory):** scp-dna, scp-gateway-resilience, scp-capability-security-review
- **Base commit:** `9c346c3d27d4077628623d57efd5887fedbde0cf`

## Problem (restate, no premature solution)

The P0 exact-$0 zero-cost wall was installed **unconditionally at import** of
`scp.llm_gateway` (Z2 PEP + Z3 router wrappers). On a deployment where
`SCP_LLM_COST_MODE` is UNSET, `validate_free_only_config()` (which defaults the mode to
`free_only`) still built the guard, and real models without a seeded pricing proof hit
`DENY_UNKNOWN_PRICE`. The exception was swallowed at higher layers → **every LLM call
returned an empty answer silently** (observed benchmark accuracy 0%). A zero-cost
*preference* had become a hard *compile-time product requirement*.

## Why-chain (DNA #1)

1. Why did benchmark accuracy drop to 0%? → every `chat()` returned empty.
2. Why empty? → the provider call was denied at `authorize_outbound`
   (`DENY_UNKNOWN_PRICE`) and the denial surfaced as an empty answer.
3. Why denied? → the zero-cost guard was active and had no fresh exact-$0 proof.
4. Why active with the knob unset? → wrappers install unconditionally AND
   `validate_free_only_config` defaults `SCP_LLM_COST_MODE` to `free_only`.
5. Root assumption to fix (owner): the $0 wall must be **opt-in**, keyed explicitly on
   `SCP_LLM_COST_MODE=free_only`; unset must mean "not installed".

## Evidence map (independent lineages)

- Static: `scp/llm_gateway/__init__.py:18-20`; `zero_cost_runtime.py` guard/`_runtime_store_path`;
  `zero_cost_guard.py:238` `validate_free_only_config`.
- Direct call-sites: `_call_openrouter.py:41`, `logical_auditor.py:190`, `multi_llm_check.py:76`
  (all call `authorize_outbound` before the network driver, catch `ZeroCostDenied` → block).
- Runtime proof (host venv, `env -u SCP_LLM_COST_MODE`): see §Verification.
- Test lineage: `tests/T05_gateway/conftest.py:35` pins `SCP_LLM_COST_MODE=free_only`
  (so wall tests enforce on opt-in), new `test_zero_cost_optin.py` proves both branches.

## Design implemented (single control point, per owner-approved plan)

Gate on the **existing** knob `SCP_LLM_COST_MODE` inside `authorize_outbound` +
`record_outbound_sent`. No new env var. Wrappers stay installed (defense-in-depth
scaffolding). `install_egress_guard` (destination/network authority) untouched — always on.

## Diff summary (before → after)

### scp/llm_gateway/zero_cost_runtime.py
- Module docstring: added note that activation is an **opt-in deployment policy**, not a
  compile-time mandate; egress authority orthogonal/always-on.
- NEW `_free_only_policy_active() -> bool`: `str(os.environ.get("SCP_LLM_COST_MODE","")).strip().lower() == "free_only"` (unset/other → False).
- `authorize_outbound(...)`: FIRST statement
  `if not _free_only_policy_active(): return _request(provider=..., model=..., task_class=..., data_class=...), None`
  → passthrough; guard/DB/validation never constructed. Rest of function (guard,
  OpenRouter one-shot catalog refresh, second authoritative decision) UNCHANGED.
- `record_outbound_sent(...)`: `if not _free_only_policy_active(): return ""` (no-op, no guard)
  before the existing `get_runtime_guard().record_sent(...)`.

### scp/llm_gateway/__init__.py
- Install logic UNCHANGED (still installs egress guard + Z2 PEP + Z3 router).
- Docstring enforcement order updated: egress always-on; Z2/Z3 "cost wall active iff
  deployment opts in with `SCP_LLM_COST_MODE=free_only` (opt-in, not compile-time mandate)".

### tests/T05_gateway/test_zero_cost_optin.py (NEW)
- `test_cost_wall_default_off_is_passthrough_and_builds_no_guard`: delenv mode →
  `authorize_outbound` returns `(request, None)`, `_guard is None`, `_store is None`,
  `record_outbound_sent` returns `""`.
- `test_cost_wall_opt_in_still_denies_unknown_price`: set `free_only` → same call raises
  `ZeroCostDenied(DENY_UNKNOWN_PRICE)` (wall authoritative when opted in).
- `test_free_only_policy_active_reads_env`: case/whitespace tolerant + every non-free_only form off.

### tests/T05_gateway/conftest.py and other T05 wall tests
- NO change (strictness preserved). conftest autouse already sets `SCP_LLM_COST_MODE=free_only`,
  so `test_provider_timeout_recovery.py`, `test_zero_cost_guard.py`, failover/egress/429 tests
  keep enforcing the wall on the opt-in branch; none weaken/skip/xfail.

### .env.example (ENV TEMPLATE)
- Added a **commented** opt-in block under the provider section:
  `# SCP_LLM_COST_MODE=` documented as default off; `free_only` = wall on. No secret, no active value.

### data/governance/proposals/PROP-zero-cost-optin-2026-09-13.md (NEW)
- Records owner directive, implemented change, and a PROPOSED (not applied) spec update;
  status `PENDING_OWNER_APPROVAL`. `spec/` NOT edited (protected).

### GA.md
- Appended §B10 handoff: owner correction compile-time → opt-in, commit S18, container
  re-run benchmark unblock. No existing content removed.

## Capability-security assessment (scp-capability-security-review)

- **Change class:** relaxes a policy from always-on to opt-in. Verdict for the *mechanism*:
  ALLOW-with-evidence — the cost decision is a deployment preference the owner explicitly
  downgraded from product mandate; it does NOT weaken destination egress authority, secret
  handling, or data-class PEP-adjacency (those remain wired and always-on).
- **Blast radius:** direct call-sites now run providers when the policy is off; when off,
  `authorize_outbound` is a pure passthrough (no DB/validate). Owner's machine opts back in
  with one env var and keeps byte-for-byte prior strictness.
- **No new capability granted:** egress allowlist (`SCP_LLM_EGRESS_ALLOWLIST` /
  `install_egress_guard`) still fail-closed on destination; cost policy is orthogonal.
- **Governance:** written spec still asserts the old mandate → left untouched; a
  `PENDING_OWNER_APPROVAL` proposal carries the intended spec change (no silent spec drift).

## Gateway-resilience assessment (scp-gateway-resilience)

- Circuit breaker / fallback cascade / provider routing code unchanged; only the cost gate's
  activation is conditioned. Off-path short-circuit avoids constructing a singleton guard/DB,
  so it cannot add latency or a new failure mode to the hot path. No privacy/data-class bypass
  introduced (data_class still forwarded into `ZeroCostRequest` on the active branch).

## Verification

- `python -m pytest tests/T05_gateway/ tests/T02_contract/test_flow_02_ask_chat_scp_standard.py tests/T01_boot/ -q`
  → **122 passed, exit 0** (0 fail). (Post-summary OpenTelemetry span-export teardown traceback
  is unrelated interpreter noise, not a test failure.)
- `python tools/t00_meta_audit.py` → "All integrity checks passed (0 new regressions)", exit 0
  (BASELINE_DEBT items are pre-existing, tracked, unrelated).
- `python tools/verify_scp_test_skill_contract.py` → `"status": "PASS_WITHIN_SCOPE"`,
  `"errors": []`, exit 0; embedded skill SHA256s match the hashes below.
- **Runtime proof, default-off (host, `env -u SCP_LLM_COST_MODE`):**
  `authorize_outbound(provider="openrouter", model="gpt-test-unknown", task_class="default")`
  → `(ZeroCostRequest(provider='openrouter', model='gpt-test-unknown', task_class='default',
  data_class=<DataClass.INTERNAL: 'INTERNAL'>), None)`; `PROOF_IS_NONE True`;
  `GUARD_NOT_CONSTRUCTED True`; `POLICY_ACTIVE False`; exit 0. No raise.

## Remaining scope / open questions (DNA #22/#23)

- PASS here means "no failure observed in the stated test scope", not "system complete".
- The four `spec/` files still describe the old mandate; they are only reconciled once the
  owner approves the proposal and a governed spec change lands.
- Opt-in-on runtime was verified only via the isolated T05 fixture (not on the host), to avoid
  creating a repo DB file under `data/foundation/`.
- Container still runs the old image; re-run benchmark after image rebuild/restart.

## Mandatory skill SHA256 (binding record)

```
scp-dna                        4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10
scp-gateway-resilience         b60e8eb3a2d2c9de971a001924019cfa0b3038f9c96dfa4e3ac1cb8fca750a5a
scp-capability-security-review 83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee
```
