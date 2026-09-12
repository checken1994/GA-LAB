# D3 — LiteLLM evaluation (assessment only, no integration)

- Date: 2026-09-12
- Worker: TD-1 (track D), branch `audit/runtime-guard-AUDIT-20260909`
- Question: Should SCP replace/augment its LLM gateway (`scp/llm_gateway/client.py`) with LiteLLM (router/fallbacks/budget/spend tracking)?
- Verdict: **KEEP core gateway.** Re-evaluate **ADOPT-PARTIAL later** only if a non-OpenAI-compatible provider becomes a hard requirement — and even then as an isolated adapter *behind* the ZeroCostGuard PEP, never as a replacement of it.

## Scope & evidence lineage

- SCP side: read directly from the repo at commit-level state of this branch (file:line citations below). Evidence level A (static) + B (components exercised by the T04/test suites).
- LiteLLM side: **public-documentation knowledge of the LiteLLM Python SDK / Proxy (router fallbacks, cooldowns, budgets & spend tracking per key/team, virtual keys, 100+ provider adapters).** This is the one lineage NOT verifiable inside this repo; mark it `INSUFFICIENT for adoption decisions` until checked against the actual LiteLLM version at any future adoption time. The verdict below is conservative: it does not depend on any LiteLLM weakness, only on SCP-specific strengths that no third-party gateway carries by construction.

## 1. What the current SCP gateway already does (evidence)

| Capability | Where (file:line) | Notes |
|---|---|---|
| Brand-neutral provider rotation | `scp/llm_gateway/client.py:640-649` | healthy-first round-robin pool (`_rr_counter`), breaker-OPEN providers pushed to the tail, load spread instead of fixed priority |
| Circuit breaker per (provider, task) | `client.py:138-177` (`CircuitBreaker`), wired `client.py:274-277` | OPEN → fast-fail without burning timeouts; HALF-OPEN allows exactly one probe; threshold/cooldown env-tunable (`SCP_LLM_BREAKER_*`) |
| Transient-retry discipline | `client.py:303-337` | 3 attempts with exponential backoff+jitter for network/5xx; 429/402 deliberately NOT retried (failover instead); breaker records one failure per decision, not per retry |
| Fallback chain | `client.py:203-214` (`TASK_FREE_FALLBACK_MAP`), `client.py:585-613` (`_provider_chain`), `client.py:419-425` (auto-router last resort) | task-specific free fallback → `openrouter/free`; caller-visible fail-closed `(None, "none")` at `client.py:429` — no fabricated answer |
| Key round-robin | `client.py:221-257` | 3 OpenRouter keys rotating per call to spread per-key rate limits |
| **$0-wall (ZeroCostGuard)** | `scp/llm_gateway/zero_cost_guard.py:225-299` | authorization = fresh immutable PricingProof AND prompt_price==0 AND completion_price==0 AND data-class policy allows (`evaluate` 252-267); everything else fails closed before the network driver (`DENY_PAID/DENY_UNKNOWN_PRICE/DENY_STALE_PRICE/DENY_DATA_CLASS`); config contract enforced `validate_free_only_config` 237-250 (`SCP_LLM_COST_MODE=free_only`, `SCP_MAX_LLM_COST_USD` must be exactly 0, paid fallback forbidden, unknown price must fail closed) |
| Pricing proofs, not name allowlists | `zero_cost_guard.py:57-84` (immutable `pricing_proofs` — UPDATE trigger raises ABORT), `free_catalog.py:1-31` (fresh catalog refresh, 6 h TTL, catalog_hash) | a model flipping free→paid produces a newer paid proof instead of staying free on a stale allowlist; proof requires `evidence_id` (epistemic provenance) |
| Transport-boundary PEP (Z2) + free-only router (Z3) | `zero_cost_runtime.py:128-153` (monkey-patched `_call_model_once` boundary), `zero_cost_runtime.py:156-241` | routing bugs cannot spend money: the PEP stays installed *underneath* Z3 (`zero_cost_runtime.py:3-6`) |
| Outbound/quota ledger | `zero_cost_guard.py:71-81` (`zero_cost_outbound_events` table), `record_event` 188-219, `record_outbound_sent` `zero_cost_runtime.py:124-125` | every authorization decision (allow/deny/shadow/actual-sent) is a durable audit row |
| Budget tier routing | `scp/core/budget_engine.py:49-63` (`route_tiers`/`order_tiers`), wired `client.py:630-634` | `SCP_BUDGET_ROUTING=1` puts free tier first per task/difficulty |
| Egress allowlist (fail-closed) | `client.py:52-87` (`_llm_egress_allowed`), `egress_policy.py:34-71` (PEP) | deny/offline/disabled → loopback fixtures only; allowlist mode requires exact host + HTTPS; unknown mode fails closed |
| Provider breadth without code change | `client.py:558-581` (`_parse_extra_providers`) | any OpenAI-compatible provider declared via `SCP_LLM_FALLBACK_PROVIDERS=name:KEY_ENV:BASEURL_ENV:MODEL_ENV` joins the chain |
| Governance protection of the wall itself | `scp/governance/drift_guard.py:107-134` | self-modification cannot introduce paid fallback / positive max-cost; `REQUIRE_GOVERNANCE` path |

## 2. LiteLLM coverage matrix (public-docs lineage, see §Scope)

| Need | LiteLLM | SCP gateway | Gap if adopting LiteLLM |
|---|---|---|---|
| Rotation / fallbacks / retries / cooldown | Yes (Router with fallbacks, cooldowns, retries) | `client.py:640-649`, `138-177`, `303-337` | none — parity |
| Provider breadth (non-OpenAI-compatible SDKs) | Yes (its main strength) | only OpenAI-compatible via env (`client.py:558-581`) | **this is the only real LiteLLM win** |
| Spend/budget tracking | Yes (per key/team budgets, spend logs) | quota/decision ledger `zero_cost_guard.py:71-81` | LiteLLM spend tracking is an *accounting* feature (estimates after/before call from price metadata); SCP's wall is *authorization before the network driver with immutable, evidence-backed proofs* — a different, stronger contract |
| Fail-closed $0 authorization with provenance | No equivalent documented (budgets limit spend; unknown-price handling is not a fail-closed authorization with evidence-id provenance and immutability) | `zero_cost_guard.py:252-289` | **adopting LiteLLM would move the money decision out of SCP's audited boundary** |
| Data-class privacy gate on outbound | No equivalent documented | `zero_cost_guard.py:263-266` + `governance/privacy.py` `PrivacyWriteGate` | would need a re-implementation anyway |
| Fail-closed egress allowlist PEP | Not a documented core feature (custom callbacks possible) | `client.py:52-87`, `egress_policy.py` | would need re-wiring |
| Governance invariant protection | n/a | `drift_guard.py:107-134` blocks self-modification that weakens the wall | LiteLLM config is outside this invariant net |

## 3. Why KEEP (evidence-based reasoning)

1. The differentiating capabilities — $0-wall with immutable fresh proofs (`zero_cost_guard.py:252-267`), decision/quota ledger (`zero_cost_guard.py:188-219`), data-class privacy gate (`:263-266`), fail-closed egress (`client.py:52-87`), and governance protection of the wall itself (`drift_guard.py:107-134`) — are SCP-specific control-plane invariants that LiteLLM does not provide by construction (per §2). Replacing the gateway would mean re-implementing all of them *on top of* LiteLLM's callback system, i.e. keeping all the work and adding a dependency + a second policy language.
2. What LiteLLM would add today (provider breadth) is already partially covered without a dependency: `SCP_LLM_FALLBACK_PROVIDERS` (`client.py:558-581`) accepts arbitrary OpenAI-compatible providers. The remaining unmet need is non-OpenAI-compatible SDKs, which is currently a hypothetical, not a workload fact observable in this repo.
3. Integration risk is asymmetric: the ZeroCostGuard PEP sits exactly at `_call_model_once` (`zero_cost_runtime.py:128-153`). Any transport swap must re-prove that boundary; a mistake there converts a routing bug into a money bug — the precise class of incident the wall exists to prevent.

## 4. Conditional future path (ADOPT-PARTIAL, only if triggered)

Trigger: a hard requirement for a provider that is not OpenAI-compatible and not declarable via `SCP_LLM_FALLBACK_PROVIDERS`.

Then: adopt LiteLLM **as one more provider adapter** behind the existing chain (an `EnvCompatProvider`-shaped wrapper), with the non-negotiable invariants kept in front and unchanged:
- `install_openai_compatible_provider_pep` PEP wrapping the adapter's call boundary (`zero_cost_runtime.py:128-153`);
- `authorize_outbound` before every candidate (`zero_cost_runtime.py:85-121`);
- egress check + ledger unchanged;
- drift-guard invariants extended to cover the new adapter's config files.

Never adopt the LiteLLM Proxy as the SCP-facing gateway: it would bypass the task-routed chain, the breaker/pool stats contract (`client.py:739-754`) and the PEP placement.

## 5. Limitations (DNA #22/#23)

- LiteLLM capabilities are asserted from public documentation knowledge, not from a pinned version verified in this environment; re-verify at any adoption time.
- No runtime benchmark of either gateway was run (this is an S-assessment; evidence level A/B for SCP code as cited).
- Verdict scope: KEEP within the current workload (OpenRouter + OpenAI-compatible providers, free-only mode). PASS_WITHIN_SCOPE only.
