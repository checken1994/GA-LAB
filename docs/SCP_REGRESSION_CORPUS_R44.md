# SCP Regression Corpus R44

## Purpose

This corpus is a regression and observability artifact, not a truth database. It preserves historical runtime cases so SCP can replay routes, verdict states and attack probes without treating its own previous output as an external ground truth.

## Case contract

Each case must contain the following fields:

| Field | Requirement |
|---|---|
| `case_id` | Stable SHA-256-derived ID from source lineage, source event ID and normalized input. |
| `source_lineage` | One of `threat_simulator`, `benchmark`, `real_pc_probe`, `reality_test`, or `unknown`. Shared-origin rows must retain the same lineage. |
| `source_artifact` | Relative artifact path and SHA-256 digest captured at extraction time. |
| `source_event_id` | Original DB/log identifier when present; otherwise `null`. |
| `input` | Redacted replay input, never a secret or full production configuration. |
| `observed_output` | Historical SCP verdict/route/status. This is an observation, not a truth label. |
| `ground_truth` | `null` unless independently adjudicated outside the original event lineage. |
| `provenance` | Capture timestamp, extractor version, source hash and redaction status. |
| `replay_policy` | `read_only`, `bounded`, and `no_policy_promotion` must be true. |

A row is invalid if it presents a historical `PASS` or `FAIL` as `ground_truth` without an independent evidence reference. A row is also invalid if its source hash is missing, its lineage is unknown without an explicit reason, or its input contains redacted-secret markers that were not handled.

## Lineage separation

The corpus must be partitioned before scoring. `threat_simulator` rows measure simulator/regression recurrence. `benchmark` rows measure benchmark replay stability. `real_pc_probe` rows measure wiring behavior on the user's machine. `reality_test` rows require a valid row-level boolean contract; the current 73-row artifact with `pass=null` is rejected and remains quarantine-only.

Rows from one source lineage are not independent samples. Counts and metrics must report lineage-specific totals and must not combine repeated simulator rows into a claim of external accuracy.

## A/B contract for BareExceptPass

The candidate rule is evaluated as an operational code-fix rule, not as a forecast or truth model. The baseline is the current scanner/fixer behavior. The treatment is the candidate rule applied in an isolated copy of the same source corpus.

The minimum A/B report must include:

| Metric | Meaning |
|---|---|
| `cases_total` | Number of source cases in the bounded corpus. |
| `baseline_findings` / `candidate_findings` | Findings produced before and after the candidate. |
| `true_positive_evidence` | Only findings confirmed by an independent test or explicit source evidence. |
| `false_positive_evidence` | Candidate changes rejected by an independent test or contradiction. |
| `unchanged_cases` | Cases with identical result and digest. |
| `behavior_flips` | Cases where the candidate changes a result; every flip requires review. |
| `compile_pass` and `fault_injection_pass` | Independent gates, not inferred from the A/B diff. |
| `policy_promotion` | Must remain `false` during this phase. |

Promotion is blocked when any case changes without a reason, when candidate output is not reproducible, when the source corpus hash changes during the run, when a finding has no verification evidence, or when any production/policy file is modified. A smaller positive result is preferable to a broad unverified improvement.

## Expected interpretation

A successful replay means the current implementation reproduced a historical observation within the recorded scope. It does not prove the historical observation was correct. A successful candidate-rule A/B means the candidate changed the operational scanner behavior under independent tests. It does not authorize active-policy promotion until R43 materialization, rollback, and behavior-consumer measurement pass.
