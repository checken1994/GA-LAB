# SCP Forecast Loop R44 — Locked, Quarantined, Fail-Closed

**Status:** `PROSPECTIVE_LOCKED_UNRESOLVED`  
**Scope:** evaluation lane only; no automatic KB/policy mutation  
**Compatibility:** additive to R43 policy handoff and learning staging

## Why this lane is separate

The historical v4 registry contains 210 prospective rows, but every row is still `outcome_code=9`. The rows are therefore not verified knowledge and must not be imported directly into `knowledge`, `error_history`, `experiences`, or `active_policies.json`. R43's reflector already treats `VERDICT_*` history as distinct from valid policy lessons. R44 keeps that boundary explicit in code.

The older `scp/prediction/predictive.py` loop remains a legacy predictive experiment. It creates questions, stores pending predictions, fetches actuals and learns from errors, but it does not provide the immutable registry anchor, case-level adjudication evidence, or calibration contract required for this 210-case audit. R44 does not silently replace it; it introduces a safer adapter for locked registries.

## Components

| Component | Path | Role |
|---|---|---|
| Registry loader | `scp/forecast/ledger.py` | Validates case schema, IDs, outcome codes and snapshot hash status. |
| Resolution ledger | `scp/forecast/ledger.py` | Append-only JSONL events; never edits the registry and never writes KB/policy. |
| Scorer | `scp/forecast/scoring.py` | Scores only resolved binary rows with numeric probabilities; unresolved rows are excluded. |
| CLI | `scripts/forecast/r44_forecast_loop.py` | Read status, record unresolved observation, or submit an evidence-backed resolution. |
| Contract tests | `tests/test_forecast_ledger_r44.py` | Tests mismatch rejection, evidence gate, immutability, unresolved exclusion and scoring. |

## Resolution contract

A resolved case requires all of the following: a verified registry anchor, an outcome code from 1–8, an HTTPS/HTTP evidence URL, a SHA-256 digest of the captured evidence snapshot, an adjudicator identifier, and a resolution timestamp. The ledger stores the digest and metadata, not arbitrary raw web content. If the registry anchor is unverified, the operation is recorded as `resolution_rejected` and returns a non-zero CLI status. A resolver failure never becomes a truth label.

The currently published v4 file has `manifest_status=MISMATCH` under the R44 canonical-hash contract because its embedded manifest digest does not match either the raw JSON bytes or the canonical JSON without the manifest field. This is an integrity finding, not a forecast outcome. Until the canonicalization/hash contract is corrected and independently reproduced, R44 will not accept a resolved outcome for that snapshot.

## Scoring contract

A score requires a case-level numerical probability and a resolved binary actual value. The scorer returns `NO_RESOLVED_FORECASTS` rather than a zero score when there are no eligible rows. It reports Brier score, a frequency baseline, skill relative to that baseline, threshold accuracy, and calibration buckets. The frequency baseline is a reference calculated from the resolved sample; it is not an out-of-sample skill estimate. For non-independent URL/claim clusters, the eventual report must use cluster-aware uncertainty rather than treating 210 rows as independent.

## Safe command examples

```powershell
python scripts/forecast/r44_forecast_loop.py `
  --registry path\to\registry.json `
  --ledger data\forecast-outcomes-r44.jsonl status
```

```powershell
python scripts/forecast/r44_forecast_loop.py `
  --registry path\to\registry.json `
  --ledger data\forecast-outcomes-r44.jsonl unresolved VR4-PAP-001 `
  --reason "Milestone not reached; no admissible evidence yet"
```

A resolution command is intentionally strict and should be run only after an independent verifier has captured the evidence snapshot and produced its SHA-256 digest.

## What R44 does not do

R44 does not claim that any of the 210 forecasts is correct or incorrect. It does not use `FRAUD`, `REFINE`, or `LEGITIMATE` as truth labels. It does not promote forecast results into policy. Policy impact remains gated by the R43 materializer, a fixed A/B corpus, behavior-delta evidence, rollback, and a separate human review.

## Evidence reference

The audit report and generated analysis artifacts are kept outside the production runtime during this staging step: `forecast_phase1_evidence.md`, `forecast_phase2_methodology_findings.md`, `forecast_phase3_r43_alignment.md`, `forecast_registry_audit.json`, `forecast_methodology_audit.json`, and `forecast_dependence_summary.json`.
