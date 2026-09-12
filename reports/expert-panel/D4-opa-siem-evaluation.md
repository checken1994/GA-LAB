# D4 — OPA/Rego (governance) + PagerDuty/SOAR (alerting) evaluation (assessment only)

- Date: 2026-09-12
- Worker: TD-1 (track D), branch `audit/runtime-guard-AUDIT-20260909`
- Question (a): replace/augment `scp/governance/` drift guard with OPA/Rego?
- Question (b): replace/augment `scp/risk_intelligence/` alert routing with PagerDuty / SOAR webhook alerting?
- Verdict: (a) **KEEP** the in-process governance. (b) **ADOPT (small)** — an outbound, export-only PagerDuty-compatible webhook exporter *behind the existing approval gates*; **KEEP** the human-authority routing model; **do NOT** adopt SOAR-style automated response.

## (a) Governance / drift guard vs OPA/Rego

### What exists today (evidence, file:line)

| Capability | Where | Notes |
|---|---|---|
| Manifest-driven protected invariants | `scp/governance/drift_guard.py:48-63` + `spec/protected_invariants.yaml` (schema_version pinned at `drift_guard.py:52-53`; 11 protected invariant ids incl. `scp.dna`, `complete_scp.reference`, `test.integrity`, `capability.pep`, `secret.boundary`) | path patterns with `/**` prefix semantics and fnmatch (`drift_guard.py:56-63`) |
| Semantic-equivalence check (not textual) | `drift_guard.py:72-98` | Python AST dump / YAML / JSON parse comparison — comment/whitespace-only edits do not trigger governance |
| Hard invariants (always DENY) | `drift_guard.py:100-151` | zero-cost wall: paid-fallback / positive `SCP_MAX_LLM_COST_USD` cannot be introduced (`:107-121`); `spec/complete_scp_reference.yaml` zero-cost fields pinned (`:122-134`); test-weakening tokens (`pytest.skip/xfail/assert True`) flagged on NEW introduction only (`:138-149`) |
| Four-value decision with fail-closed epistemics | `drift_guard.py:26-45`, `:153-192` | ALLOW / REQUIRE_GOVERNANCE / DENY / **UNKNOWN** — an unparseable protected change is UNKNOWN, never implicit approval (`:171-180`) |
| Batch aggregation, worst-severity wins | `drift_guard.py:194-214` | |
| Product wiring | `scp/core/code_evolution_agent.py:25,54` (`DriftGuard(spec/protected_invariants.yaml)` gates candidate writes); `scp/autofix/engine.py` imports drift guard | candidate source changes pass DriftGuard before any write |
| Adjacent governance surfaces | `scp/governance/privacy.py:64+` (`PrivacyWriteGate`, policy from `spec/data_policies.yaml`), `scp/governance/retention.py` | data-class policy decisions consumed by the zero-cost wall (`zero_cost_guard.py:263-266`) |

### OPA/Rego fit analysis

1. **Policy language vs. policy substance.** The hard part of the drift guard is not policy evaluation but *input preparation*: Python AST equivalence (`drift_guard.py:73-77`) must be computed in Python anyway. Rego cannot parse Python source; OPA would receive pre-digested documents, i.e. all real logic stays in Python and Rego would only re-express `if matched and not authorized → REQUIRE_GOVERNANCE` (`drift_guard.py:182-192`).
2. **Single source of truth.** Moving decisions to Rego bundles creates two encodings of the same invariants (Python hard invariants `:100-151` + Rego). Divergence between them is itself a drift risk — the exact class of failure this guard exists to prevent.
3. **Fail-closed parity risk.** DriftGuard's UNKNOWN-on-unparseable (`:171-180`) is deliberate epistemics. OPA's undefined-result semantics would need careful mapping to avoid silently converting UNKNOWN → ALLOW during a port (classic fail-open regression).
4. **Deployment cost.** OPA adds a sidecar/service or embedded engine, bundle distribution and availability concerns — a new dependency for zero additional invariant coverage at SCP's current scale (11 invariants, 2 in-process callers).
5. Where OPA *would* make sense later: if external actors (CI, dashboards, other services) need to query the same policy decisions over an API. Today `code_evolution_agent.py:54` and the autofix engine are the only decision points, both in-process.

### Verdict (a): KEEP

Keep DriftGuard + `protected_invariants.yaml` as the authority. Record OPA as a candidate only for a future "policy decisions as a service" need; any port must preserve the UNKNOWN decision and add a divergence test (same inputs → same decision in both engines) before OPA could be trusted.

## (b) alert_router / risk_intelligence vs PagerDuty / SOAR webhook

### What exists today (evidence, file:line)

| Capability | Where | Notes |
|---|---|---|
| No-default-right-to-alert contract | `scp/risk_intelligence/alert_router.py:1-19` | `FORBIDDEN_BROADCAST_OPERATIONS` (post_social, mass_sms, emergency_call, public_alarm) → `DENY_FORBIDDEN_OPERATION` (`:37-44`) |
| Authority routing | `alert_router.py:21-27,45-46` | CYBER→SOC, HEALTH→HEALTH_AUTHORITY, FIRE→AUTHORIZED_EMERGENCY_CONTACT, INFRASTRUCTURE→UTILITY_OPERATOR, INTERNAL→SCP_ADMIN |
| Unconfigured connector → evidence only | `alert_router.py:52-59` | `BUNDLE_ONLY` + `EmergencyEvidenceBundle` (`evidence_bundle.py:18+`) — alerting failure can never lose the evidence |
| Approval gate | `alert_router.py:60-66` | configured + `requires_approval` → `WAITING_APPROVAL` (human authority in the loop) |
| Pre-authorized bounded delivery | `alert_router.py:67-72` | `SUBMITTED` with `bounded_incident_report` delivery record |
| Incident lifecycle | `incident_state.py:1-42` (`IncidentStateMachine`, OBSERVED → … → RESOLVED transitions table) | |
| Risk classification | `risk_classifier.py:18-51+` (`RiskLevel` PR-levels, `RiskClassifier.classify`) | |
| Containment stays capability-gated | `containment.py:13-17` (`ContainmentCoordinator` requires `CapabilityAuthority`) | automated response is capability-scoped, not alert-triggered |
| Existing webhook surface (inbound) | `scp/api/webhook.py:43+` (`/api/analyze`, admin-auth `_require_admin` `:86-96`, `RequestRunLedger` `:44`) + `webhook_url` field `:76` | inbound API for external systems; **no outbound network alert delivery exists** — `deliveries` in `alert_router.py:71` is a decision record, not a transport |

### Gap analysis

The router is a decision authority without a transport. When a human authority *has* pre-authorized a channel, nothing actually pages anyone: the "SUBMITTED" delivery is recorded, not sent. A PagerDuty-compatible (Events API v2-shaped) endpoint is the industry-neutral way to reach on-call humans (PagerDuty, Opsgenie-compatible receivers, self-hosted receivers) and, with a different endpoint shape, SIEM ingestion (CEF/JSON webhook receivers).

### Verdict (b): ADOPT (small, export-only) + KEEP the authority model

Recommended shape (when implemented — NOT in this task):
1. **Export-only delivery adapter** implementing the `deliveries` step for the `SUBMITTED` path (`alert_router.py:67-72`): POST a bounded incident report (routing_key/dedup_key/summary/severity/source — Events API v2 field names) to the configured channel endpoint. The router's decision logic, forbidden-operation deny list, `BUNDLE_ONLY` and `WAITING_APPROVAL` semantics stay exactly as they are — the adapter is a *transport*, never an authority.
2. **Fail-closed delivery**: endpoint unreachable/time-out → keep `BUNDLE_ONLY` evidence + record the failed delivery in the ledger (same spirit as `alert_router.py:52-59`); no retry storm, no uncertain external side-effect repetition (AGENTS.md side-effect discipline).
3. **Egress discipline**: the exporter goes through the same allowlist/fail-closed egress contract as the LLM path (`client.py:52-87` pattern) — alert endpoints are egress destinations and must be allowlisted explicitly.
4. **Audit**: every delivery attempt lands in a run ledger (the `RequestRunLedger` pattern already used by `scp/api/webhook.py:44`).
5. **Keep FORBIDDEN_BROADCAST_OPERATIONS absolute**: PagerDuty-style paging is a 1:1 authorized-channel notification, not public broadcast; the deny list (`alert_router.py:14-19`) remains untouched.

Explicitly NOT recommended: SOAR-style automated playbooks (auto-containment/auto-remediation triggered by alerts). Containment already requires `CapabilityAuthority` (`containment.py:14`); putting response automation behind an external SOAR would move SCP's human-authority boundary outside the audited kernel.

### Verdict (b) summary

- **ADOPT**: PagerDuty-compatible webhook exporter as a small, export-only, approval-gated delivery transport (low risk, closes the real "nobody gets paged" gap, reuses existing egress/ledger/approval primitives).
- **KEEP**: `AlertRouter` decision authority, forbidden-broadcast deny list, approval gating, incident state machine, capability-gated containment.

## Limitations (DNA #22/#23)

- Static (level A) evidence: no live OPA/PagerDuty integration was tested (none exists in the repo — verified by grep: no `pagerduty`/`siem`/`splunk` references in `scp/`).
- Line numbers refer to this branch's working tree at assessment time (base `45a7dc8` + TD-1 commits).
- No code was integrated in this task, per scope.
