# SCP Systems Audit & Optimization Plan

## 1. Executive Summary
This document provides a comprehensive audit and optimization plan for the SCP project, covering major components M4 (Epistemic Runtime), M5 (Immutability), M6 (Governance), M7 (Acquisition), and M8 (Knowledge). The audit also includes a rigorous check against the FA-01 to FA-07 rules (SCP DNA), test integrity, and system architecture invariants.

## 2. Architecture & Code Quality Audit

### M4 & M5: Epistemic Runtime & Immutability
- **Location:** `scp/epistemic/`, `scp/persistence/`, `scp/task_kernel.py`
- **Findings:** The `evidence_store.py` securely enforces immutability. Blob writes are highly crash-ordered (`staging -> fsync -> atomic rename`), preventing partial writes. Tampered metadata fails safely (FAIL CLOSED). HMAC-SHA256 is used for depth defense. 
- **Quality:** Excellent adherence to the *Reality > Model* and fail-closed invariants. No path hardcoding observed.

### M6: Governance
- **Location:** `scp/governance/`
- **Findings:** Contains distinct authorities for constraints, e.g., `drift_guard.py`, `dangerous_knowledge.py`, `privacy.py`. These enforce constraints on execution cleanly.

### M7: Acquisition (Internet / S03)
- **Location:** `scp/data_sources/`, `scp/web_control/`
- **Findings:** Robust separation of domains (69 distinct files in `data_sources/` ensuring specialized handlers). `web_control` handles browser sessions and internet searching properly, ensuring isolated scopes.

### M8: Knowledge (S06)
- **Location:** `scp/knowledge/`
- **Findings:** Complex orchestration via `cognitive_orchestrator.py`, `claim_extractor.py`, `antibody_system.py`, and `source_reputation.py`. The design inherently limits knowledge poisoning by utilizing isolated source evaluation.

## 3. Test Integrity & FA-01 to FA-07 Compliance

- **FA-01 (No loosen assertion):** Meta-audit strictness correctly rejects lowered testing thresholds.
- **FA-02 (No delete/skip/xfail test):** Full validation via regex on the codebase and `meta_audit.py` confirms that `pytest.skip` and `pytest.mark.xfail` are strictly policed. Legitimate skips exist ONLY for OS constraints (e.g., `Job Object sandbox is Windows-specific` in `test_os_sandbox.py`).
- **FA-03 to FA-07 Enforcement:** Validated. A full `pytest` run confirmed tests execute correctly. `tests/T11_release`, `tests/T05_gateway`, and `tests/T04_kernel` yield passing results ensuring baseline correctness.

## 4. Discrepancies & Issues Identified

1. **Task Kernel State Machine Inconsistency:**
   - *Documentation (`AGENTS.md` / `scp-task-kernel-review`):* States that the Task Kernel has **15** valid states.
   - *Implementation (`scp/task_kernel.py`):* The `STATES` set actually defines **17** states (`CREATED, PLANNING, READY, QUEUED, LEASED, RUNNING, WAITING_TOOL, VERIFYING, CHECKPOINTED, UNKNOWN, RECOVERING, RECONCILING, HUMAN_REVIEW, RETRY_SCHEDULED, COMPLETED, FAILED, CANCELLED`). 
   - *Impact:* While the atomic transitions are strict, the state mismatch violates the exact documentation constraint and may cause confusion during architecture reviews.
2. **Dependency Warnings during runtime:**
   - Running `pytest` emits `RequestsDependencyWarning: urllib3 (2.7.0) or chardet (6.0.0.post1)/charset_normalizer (3.4.3) doesn't match a supported version!` due to mismatched `requests` library versions.

## 5. Optimization & Action Plan

1. **Reconcile Task Kernel States:** 
   - Update the Task Kernel documentation and the exact `AGENTS.md` manifest to match the 17 states implemented in code, or refactor `task_kernel.py` to remove 2 states if they are redundant.
2. **Dependency Resolution:**
   - Resolve the `requests` library dependency mismatch in `requirements.txt` to eliminate runtime warnings and prevent potential underlying HTTP transport bugs.
3. **Continuous Verification Performance:**
   - With the test suite expanding to encompass all components M4-M8, `pytest` runtime is increasing. Recommend partitioning integration and unit tests further, utilizing `pytest-xdist` for parallel execution without breaking state isolation.
4. **Epistemic Runtime Cleanup:**
   - While `.staging` directory is cleaned up in `evidence_store.py` (`C1 reconciliation`), ensure this process does not encounter race conditions when multiple workers initialize concurrently.
