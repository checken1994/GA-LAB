# DISPATCH — 2026-09-08T01:30:31Z

## 2026-09-08T01:30:31Z
You are Worker 1 (teamwork_preview_worker).
Your working directory is: c:\Users\check\Downloads\scp\.agents\worker_1

AUTHORITATIVE DOCUMENTS TO READ FIRST:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (MANDATORY: read this first!)
- c:\Users\check\Downloads\scp\.agents\orchestrator_9\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\explorer_1\handoff.md
- c:\Users\check\Downloads\scp\.agents\explorer_2\handoff.md
- c:\Users\check\Downloads\scp\.agents\explorer_3\handoff.md
- c:\Users\check\Downloads\scp\tools\probes\probe_gap12_delta_audit.py
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

EXCLUSIVE FILE WRITE OWNERSHIP:
You own and may modify ONLY the following files:
1. `scp/task_kernel_parts/taskkernel.py` (and `scp/task_kernel.py` if needed for imports/exports)
2. `scp/ask_kernel_adapter.py`
3. `scp/hands/task_kernel_bridge.py`
4. `tests/T04_kernel/test_adversarial_kernel_flaws.py`
You MUST NOT modify any other files.

IMPLEMENTATION INSTRUCTIONS:
1. In `scp/task_kernel_parts/taskkernel.py`:
   - Extend transition guard at line 253 for ("COMPLETED", "FAILED").
   - Update `_assert_lease()` signature to `(self, lease_id: str, task_id: str, actor: str | None = None)` and verify actor matching.
   - In `_schema()`, add `attempts` and `error` columns to `tasks`.
   - Implement `commit_failed()`.
2. In `scp/ask_kernel_adapter.py`:
   - Update `fail()` to call `commit_failed()`.
3. In `scp/hands/task_kernel_bridge.py`:
   - Update lines 445 and 582 to call `commit_failed()`.
4. In `tests/T04_kernel/test_adversarial_kernel_flaws.py`:
   - Add tests covering all 9 branches.
5. Verification commands:
   - `python tools/probes/probe_gap12_delta_audit.py` -> ALL_VECTORS_PROTECTED_GREEN
   - `pytest tests/T04_kernel -q`
   - `pytest tests/T03_capability/test_hands_authority_pep.py -q`
   - `pytest tests/ -q`
   - `python tools/t00_meta_audit.py`
   - `git diff scp/`
