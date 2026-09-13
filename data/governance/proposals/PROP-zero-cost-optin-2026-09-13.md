# PROP-zero-cost-optin — Zero-cost wall: compile-time mandate → opt-in deployment policy

- **ID:** PROP-zero-cost-optin-2026-09-13
- **Date:** 2026-09-13
- **Author:** SCP Worker Agent S18
- **Branch:** `audit/runtime-guard-AUDIT-20260909`
- **Base commit (before change):** `9c346c3d27d4077628623d57efd5887fedbde0cf`
- **Delivered in commit:** S18 — `fix(gateway): zero-cost wall opt-in via SCP_LLM_COST_MODE=free_only (was compile-time mandate) [owner directive]`
- **Status:** `PENDING_OWNER_APPROVAL`
- **Spec touched by this proposal:** NO (spec/ is protected and untouched). This document only proposes a downstream governance edit for owner approval.

## 1. OWNER DIRECTIVE (verbatim intent, 2026-09-13)

> "tôi chỉ bảo dùng API free cho trường hợp của tôi, CHỨ KHÔNG phải mã hóa cứng bắt buộc SCP đòi API free — xóa cái này đi."

Interpretation: free-only zero-cost is a **deployment preference for the owner's own
machine**, NOT a hard-coded compile-time mandate that SCP imposes on every deployment.
The $0 wall must become **opt-in**, active only when a deployment itself configures
`SCP_LLM_COST_MODE=free_only`.

## 2. What was wrong

`scp/llm_gateway/__init__.py` installs the Z2 zero-cost PEP and the Z3 free-only
router **unconditionally at import**. Combined with the direct call-sites that call
`authorize_outbound` before the network driver, a deployment that leaves
`SCP_LLM_COST_MODE` unset still got an active wall whose `validate_free_only_config()`
defaulted to `free_only`. Real paid/free models with no seeded pricing proof then hit
`DENY_UNKNOWN_PRICE`, the exception was swallowed at higher layers, and **every LLM
call returned an empty answer silently** (the reported benchmark accuracy 0%).
This made a zero-cost policy behave like a mandatory product requirement.

## 3. Implemented change (this commit)

Single control point: the internal gate `authorize_outbound` /
`record_outbound_sent` in `scp/llm_gateway/zero_cost_runtime.py`, keyed on the
**existing** knob `SCP_LLM_COST_MODE`:

- New `_free_only_policy_active()` → True only when
  `SCP_LLM_COST_MODE == "free_only"` (trimmed, lower-cased). Default/unset → False.
- When inactive, `authorize_outbound` short-circuits to `(request, None)` before any
  guard/DB/validation is constructed (passthrough), and `record_outbound_sent` is a
  no-op returning `""`.
- The Z2/Z3 wrappers remain installed (defense-in-depth scaffolding unchanged); when
  the policy is opted in, they call the now-active wall exactly as before.
- `install_egress_guard` (destination/network authority) is **orthogonal and always
  on** — not part of the cost policy, not changed.
- No new env var introduced; the owner's machine, which sets
  `SCP_LLM_COST_MODE=free_only`, keeps 100% of the previous strict behavior.

## 4. Proposed spec update (for owner approval via governance flow)

The four protected spec files still describe the zero-cost wall as if it were an
unconditional requirement. The following edits are proposed so the written spec matches
the intended opt-in semantics. They are NOT applied here.

- `spec/complete_scp_reference.yaml` → `intelligence.zero_cost`: add that the requirement
  describes the **policy semantics when active**, and that activation itself is a
  deployment choice gated by `SCP_LLM_COST_MODE=free_only`.
  (current keys: `required: true`, `max_cost_usd: 0`, `unknown_price_policy: DENY`,
  `paid_fallback: false`)
- `spec/implementation_bindings.yaml` → `intelligence.zero_cost`: keep the two
  implementations bound; clarify `required_now` refers to the capability being wired
  and opt-in-enforceable, not always-enforcing.
- `spec/llm_outbound_paths.yaml`: keep every path `GUARDED`/`GUARDED_GATEWAY` (the PEP is
  wired in all paths); add a note that the guard is a no-op passthrough while the
  cost policy is not opted in, so path classification is about *capability*, not
  *always-active enforcement*.
- `spec/data_policies.yaml` (line ~15 "no bypass for egress, zero-cost proof, or secret
  scanning"): unchanged for egress/secret; the "zero-cost proof" clause should be read
  as "no bypass **while the zero-cost policy is active**".

## 5. Evidence / non-degradation

- Added `tests/T05_gateway/test_zero_cost_optin.py` proving BOTH branches (default off →
  passthrough, guard never built; opt-in on → `DENY_UNKNOWN_PRICE` still raised). This
  **increases** coverage (FA-01: no skip/xfail/weakening).
- Existing T05 wall tests keep enforcing via the T05 `conftest.py` autouse precondition
  `SCP_LLM_COST_MODE=free_only`; none were loosened.
- Green: `tests/T05_gateway/ + tests/T02_contract/test_flow_02_ask_chat_scp_standard.py +
  tests/T01_boot/` = 122 passed, exit 0. `tools/t00_meta_audit.py` = 0 new regressions.
  `tools/verify_scp_test_skill_contract.py` = PASS_WITHIN_SCOPE, exit 0.
- Runtime proof (host, env unset): `authorize_outbound(provider="openrouter",
  model="gpt-test-unknown", ...)` returned `(ZeroCostRequest(...), None)`, no raise,
  `_guard is None`.

## 6. Decision requested

Owner to approve/adjust §4 and, on approval, apply the spec edits through the normal
governance flow (separate change with its own review). Until approved, the spec files
remain unmodified and this proposal stays `PENDING_OWNER_APPROVAL`.
