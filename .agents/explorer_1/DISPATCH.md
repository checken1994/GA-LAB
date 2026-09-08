## 2026-09-08T01:22:38Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Explorer 1 (teamwork_preview_explorer).
Your working directory is: c:\Users\check\Downloads\scp\.agents\explorer_1

AUTHORITATIVE DOCUMENTS TO READ FIRST:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (MANDATORY: read this first!)
- c:\Users\check\Downloads\scp\.agents\orchestrator_9\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\orchestrator_8\handoff.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

EXPLORATION MISSION:
You are a READ-ONLY explorer. Do NOT modify any code.
Focus on TaskKernel core implementation:
1. Deep-dive into `scp/task_kernel_parts/taskkernel.py` (and `scp/task_kernel.py`).
2. Examine lines 250-362 of `taskkernel.py`:
   - Inspect line 253 where `to_state == "COMPLETED"` is guarded with `InvalidTransition`.
   - Analyze how to extend this guard to block direct transition to `"FAILED"`:
     `if to_state in ("COMPLETED", "FAILED"): raise InvalidTransition(...)`
   - Inspect `_assert_lease()`: how it is called, how it queries the `leases` table, and how to verify `actor` matches `lease_row["worker_id"]` when `actor` is supplied.
3. Formulate the precise implementation specification for `commit_failed()`:
   - Method signature: `def commit_failed(self, task_id: str, lease_id: str, actor: str, failure_classification: str, indictment_ref: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:`
   - How `_assert_lease(task_id, lease_id, actor=actor)` or equivalent should be executed.
   - Retry budget logic: fetch task row (`attempts`, `max_attempts`), determine if failure is retryable (e.g. `failure_classification.upper() in ("RETRYABLE", "TRANSIENT")` or based on error classification) AND `attempts < max_attempts`.
   - If retryable: what target state? (`UNKNOWN` or `RETRY_SCHEDULED`), increment `attempts = attempts + 1`, clear active lease or set retry backoff. Check what states exist in `STATES` enum in `task_kernel.py`.
   - If exhausted or fatal (or classification is `FATAL`, `UNRECOVERABLE`, etc.): transition to `FAILED`.
   - How to persist `indictment_ref`, `failure_classification`, and `details` to `tasks` (e.g. `error` column) and `events` (as `TASK_FAILED` or `STATE_TRANSITION` payload).
   - Check SQLite transaction atomicity and version increment.
4. Deliver a comprehensive analysis report in `c:\Users\check\Downloads\scp\.agents\explorer_1\handoff.md` and notify orchestrator via send_message.
