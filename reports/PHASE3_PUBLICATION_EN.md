# SCP Phase 3 RAG Evidence Remediation — Public Technical Announcement

**Status: candidate evidence release; not a verified RAG benchmark.**

SCP has published a fail-closed Phase 3 evidence package at commit [`a92776ffc7da1c70cc209428cb224494c816471e`](https://github.com/checken1994/GA-LAB/commit/a92776ffc7da1c70cc209428cb224494c816471e). The release preserves the historical 50-row candidate dataset and adds a versioned JSONL/CSV/XLSX review ledger, independent-source fetch metadata, exact source-contained machine quotes where available, a strict validator, a real Ragas runner, an ARES precondition audit, and a proof-gap matrix.

This release deliberately does **not** claim that the 50 questions are verified Gold, that Ragas produced an official score, that ARES was executed, or that the 1,000-question benchmark is complete. Those claims would be stronger than the evidence currently supports.

| Item | Observed result | Release interpretation |
|---|---:|---|
| Phase 3 rows | 50 unique IDs | Structurally complete candidate ledger |
| Machine-contained source quotes | 9/50 | Candidate evidence only; no human review was fabricated |
| Human-verified Gold rows | 0/50 | Gold promotion blocked |
| Ragas v2 admitted rows | 0/50 | No official benchmark score |
| ARES score | `null` | Preconditions blocked |
| Isolated `/ask` pilot | 3/3 HTTP 200 | All returned `UNKNOWN`/`ESCALATE`; no factual pass claim |
| Local release gates | 172 pytest passed; compile, Ruff, Bandit medium/high, dashboard build and npm audit passed in CI | Code/artifact gate, not factual RAG proof |

## What changed

The original extractor was superseded rather than silently rewritten. The new builder never uses an answer as an evidence quote. It fetches a source independently, stores HTTP status, fetch time, content hash, cache path, canonical URL, chunk hash and quote-containment state, and keeps temporal, legal, medical and financial rows blocked until authoritative current-source review is available. Known corrupt mappings, including the previously observed CH-0036, CH-0042, CH-0049 and CH-0050 cases, remain explicitly marked `SOURCE_MISMATCH_NEEDS_REBUILD`.

The JSONL, CSV and Excel outputs are checked for the same 50 IDs and schema. The validator returned `PASS_WITHIN_SCOPE` with no row-count, duplicate-ID, hash, quote-containment or cross-format errors. This means the files are internally consistent; it does not mean that the answers are factually correct.

## Ragas and ARES methodology boundary

Ragas is designed for component-wise evaluation of an LLM/RAG pipeline, including faithfulness, answer relevancy, context precision and context recall [1]. Context precision specifically evaluates whether relevant retrieved chunks are ranked above irrelevant chunks [2]. SCP therefore added `benchmark/run_ragas_v2.py`, which calls the official `ragas.evaluate()` API only after explicit Gold admission.

The real runner was tested against recorded SCP runtime outputs. It admitted zero rows because the staged data contained 32 HTTP-429 runtime rows and 18 non-eligible candidate rows. It used no token-overlap fallback and emitted `BLOCKED_NO_VERIFIED_ROWS`. A separate one-row diagnostic called `ragas.evaluate()` with Ragas 0.1.7 and `gpt-5-mini`; the embedding endpoint returned HTTP 404 for the metrics requiring embeddings. A judge-only diagnostic completed but returned context precision 0.0, context recall 0.0 and faithfulness `NaN` after a judge parse failure. These diagnostics are evidence about execution behavior, not benchmark scores.

ARES evaluates context relevance, answer faithfulness and answer relevance using synthetic training data, lightweight judges and a human-annotated set for prediction-powered inference [3]. The official ARES repository documents three required inputs: at least 50 human-annotated query-document-answer examples, few-shot examples, and a larger unlabeled evaluation set [4]. SCP currently has none of these verified inputs and the Windows environment has no importable `ares` package. The ARES result is therefore `BLOCKED_PRECONDITIONS`, with no score.

## Runtime and release evidence

SCP was started only on isolated loopback port `127.0.0.1:8002`, with egress denied and a separate database/trace directory. The health response identified commit `e97bd879...` during the runtime pilot baseline. Three unique questions then returned HTTP 200, but all were governed as `UNKNOWN`/`ESCALATE`; the runtime was stopped and both ports 8000 and 8002 were confirmed free. The final code and artifact release was fast-forward merged to `main`, and the post-merge SCP Release Gate completed successfully at GitHub Actions run [32940493975](https://github.com/checken1994/GA-LAB/actions/runs/32940493975).

A green CI pipeline proves reproducible code gates, not universal factual correctness. The proof-gap matrix therefore keeps side-effect connector wiring, capability revocation across the tool layer, queue fairness/quota behavior, provider-timeout recovery, and the complete planner-to-audit golden-task chain as `UNPROVEN` or `STATIC_PROVEN_ONLY` where no end-to-end evidence was captured.

## Repository artifacts

| Artifact | Purpose |
|---|---|
| [`gold_anchor_50_v2_candidates.jsonl`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/gold_anchor_50_v2_candidates.jsonl) | Versioned candidate records with provenance and blocked status |
| [`gold_anchor_50_v2_review_ledger.xlsx`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/gold_anchor_50_v2_review_ledger.xlsx) | Excel review ledger with the same 50-row schema |
| [`validate_phase3_gold_v2.py`](https://github.com/checken1994/GA-LAB/blob/main/tools/validate_phase3_gold_v2.py) | Cross-format structural validator |
| [`run_ragas_v2.py`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/run_ragas_v2.py) | Official Ragas-only, fail-closed runner |
| [`ares_preconditions_v2.json`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/ares_preconditions_v2.json) | ARES precondition result with score set to null |
| [`phase3_proof_gap_matrix_v1.json`](https://github.com/checken1994/GA-LAB/blob/main/reports/phase3_proof_gap_matrix_v1.json) | Evidence-linked proof status for remaining SCP claims |

## Reddit post

**Title:** SCP Phase 3 RAG evidence remediation: 50 structurally valid candidates, 0 verified Gold rows, no fabricated Ragas/ARES score

We published a proof-first Phase 3 update for SCP. The release contains 50 unique candidate records in JSONL, CSV and Excel, independent-source fetch metadata, source-contained quotes for 9 rows, a fail-closed Ragas runner and an ARES precondition report. The validator passes the file contract, but Gold promotion remains blocked because all rows still require independent review.

We also ran the real Ragas 0.1.7 API path. The benchmark runner admitted zero rows instead of scoring candidate data. A one-row diagnostic reached `ragas.evaluate()` but failed on the embedding endpoint; the LLM-only diagnostic exposed zero context precision/recall on the observed sample. ARES was not scored because the required human-annotated, few-shot and unlabeled inputs were not present. The release is intentionally conservative: CI is green, but factual RAG quality is not claimed.

The main question for review is whether the provenance schema and admission gate are strict enough before we collect independent annotations. Please inspect the commit and artifacts rather than treating the old token-overlap output as Ragas.

## X thread

1/ SCP Phase 3 update: we published an evidence-remediation release at commit `a92776f`. It is a **candidate evidence release**, not a verified RAG benchmark.

2/ The 50-row ledger is cross-format consistent. Nine rows have source-contained machine quotes. All 50 remain candidate-only; no human review identity was fabricated.

3/ The real Ragas runner is fail-closed: 0 rows admitted, 0 proxy fallback, no official score. A diagnostic reached `ragas.evaluate()` but the embedding endpoint returned 404.

4/ ARES is `BLOCKED_PRECONDITIONS`: no verified human set, few-shot set, unlabeled evaluation set, or importable package. No ARES score exists.

5/ SCP 8002 pilot: 3/3 HTTP 200, all `UNKNOWN`/`ESCALATE`. CI and post-merge gates are green, but factual RAG and several Agent OS proof gaps remain unproven.

## References

[1]: https://docs.ragas.io/en/v0.1.21/concepts/metrics/ "Ragas Metrics — component-wise evaluation"
[2]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/ "Ragas Context Precision"
[3]: https://aclanthology.org/2024.naacl-long.20/ "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems, NAACL 2024"
[4]: https://github.com/stanford-futuredata/ARES "Stanford FutureData ARES repository and data-contract documentation"
