# Scope: SCP Agent OS Dynamic Runtime Execution Audit & Causal Chain Analysis

## Architecture & Subsystems
- **Gateway**: `scp/llm_gateway/` — External LLM boundary, zero-cost enforcement (`max_cost_usd=0`), circuit breakers, model fallback cascade.
- **TaskKernel**: `scp/task_kernel.py`, `scp/task_kernel_parts/`, `scp/kernel_storage.py` — Central state machine, SQLite WAL, monotonic lease fencing tokens, append-only event journal hash chain, checkpoints.
- **Epistemic Storage**: `scp/epistemic/evidence_store.py`, `scp/persistence/db.py` — Content-addressed blob store, crash-ordered atomic staging, append-only SQLite triggers, HMAC record integrity.
- **PolicyEngine & Security**: `scp/security/`, `scp/governance/` — AttackPolicyEngine, Windows Job Object OS sandbox, S11 governance (drift, privacy, dangerous knowledge).
- **Autofix Engine**: `scp/autofix/` — Diagnostic parsers, patch synthesizers, and runner verification phases.
- **RunnerPhases & RealityTest**: `scp/autofix/runner_phases/reality_test.py` — Dynamic smoke execution, class method discovery, async execution, BaseException handling.
- **Knowledge System**: `scp/knowledge/knowledge_runtime.py` — S06 runtime, FTS5 retrieval index, GoldLifecycle, temporal revalidation.
- **Acquisition & Scraper**: `scp/data_sources/`, `scp/core/top_systems_learning.py` — Internet document acquisition, source policy, quarantine pipeline.

## Feature Inventory (Survey Phase Findings)
| # | Feature / Investigation Focus | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | Baseline Reconcile & HEAD SHA | Verify exact commit SHA `48e5ca8dd0867d1257103ea66f73be752d785b60`, branch `experts-4.0.3-434green`, clean tree | M1 | explorer_3 |
| 2 | Full Test Suite Dynamic Execution | Live execution of `pytest tests/`, `pytest scp/tests/`, capturing verbatim terminal output, test counts, runtime duration | M1 | explorer_2, explorer_3 |
| 3 | T00 Meta-Audit Live Execution | Live execution of `python tools/t00_meta_audit.py`, verifying FA-01 to FA-07 pass and 5 baseline debts | M1 | explorer_2 |
| 4 | Test-Skill Contract Verification | Live execution of `python tools/verify_scp_test_skill_contract.py`, verifying 14 gates and 29 DNA principles | M1 | explorer_1 |
| 5 | TaskKernel 18 vs 15 States Analysis | Deep causal analysis of 18 active runtime states vs 15-state mandate in AGENTS.md, detailing RECONCILING, RETRY_SCHEDULED, WAITING_APPROVAL | M2 | explorer_1 |
| 6 | End-to-End Causal Chains Trace | Step-by-step trace of Hands Mutating Action (Computer-Use) and RAG / Ask Route lifecycles | M2 | explorer_1 |
| 7 | FA-02 Skip Paths & Technical Debt | Detailed documentation of 5 baseline debts, 4 AST evasion patterns (hooks, aliasing, broad except, partial callable) | M2 | explorer_2 |
| 8 | Epistemic EvidenceStore Crash Lifecycle | Staging, fsync, atomic rename, DB transaction, and 4 concrete failure vectors (orphan leak, unlink race, POSIX sync, lock scope) | M2 | explorer_2 |
| 9 | Benchmark vs DeepInvestigator Audit | Critical comparative evaluation: Static AST ("tĩnh sống") vs Dynamic Reality ("thực tế chết"), highlighting blind spots | M2 | explorer_3 |
| 10 | Comprehensive Reality Audit Report | Assembly and synthesis into `c:\Users\check\Downloads\scp\teamwork_runtime_audit_report.md` | M3 | all |
| 11 | Multi-Agent Review & Challenger Gate | Independent adversarial verification and review of audit report | M4 | reviewer, challenger |
| 12 | Forensic Integrity Audit Gate | Forensic integrity verification against FA-01 to FA-07 rules | M4 | auditor |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M0 | Survey Phase | Map full architecture, state machine, baseline debt, and benchmark dimensions | None | DONE |
| M1 | Dynamic Runtime Execution Track | Execute live test suites, capture verbatim terminal output, run T00 and contract verifier | M0 | IN_PROGRESS |
| M2 | Causal Chain & Benchmark Synthesis | Synthesize detailed causal chains, state machine discrepancy, and DeepInvestigator benchmark | M0 | IN_PROGRESS |
| M3 | Comprehensive Report Generation | Write `teamwork_runtime_audit_report.md` at workspace root | M1, M2 | PLANNED |
| M4 | Gate & Verification | Reviewers, Challengers, and Forensic Auditor verification | M3 | PLANNED |
