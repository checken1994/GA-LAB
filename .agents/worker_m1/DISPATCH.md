## 2026-09-07T12:09:25Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Worker M1 for Milestone 1 (GAP-05 & GAP-06).
Your working directory: c:\Users\check\Downloads\scp\.agents\worker_m1\
Authoritative user request: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
Project plan: c:\Users\check\Downloads\scp\PROJECT.md
Explorer 1 handoff & blueprint: c:\Users\check\Downloads\scp\.agents\explorer_survey_1\handoff.md
Explorer 1 analysis: c:\Users\check\Downloads\scp\.agents\explorer_survey_1\analysis.md

Files you exclusively own:
- scp/kernel_storage.py
- tests/T04_kernel/test_kernel_storage.py

Instructions:
1. Review c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md, ORIGINAL_REQUEST.md, PROJECT.md, and Explorer 1's handoff.
2. Implement GAP-05 & GAP-06 in scp/kernel_storage.py:
   - Ensure SQLiteKernelStorage has zero RLock or _tx_lock (verifying that concurrency relies strictly on database-level SQLite WAL BEGIN IMMEDIATE and OCC).
   - In make_storage(db_path: str | Path) -> SQLiteKernelStorage:
     - Add explicit docstring WARNING:
       """WARNING: SQLite is a Single Point of Failure (SPOF) in distributed deployments.
       It does not support cross-node replication or active-active clustering.
       For high availability or multi-node production setups, a distributed storage backend is required."""
     - Read os.environ.get("SCP_STORAGE_BACKEND", "sqlite").strip().lower().
     - If backend in ("sqlite", ""): return SQLiteKernelStorage(db_path).
     - If any other backend (e.g. "postgres", "mysql"): raise NotImplementedError(f"Unsupported storage backend '{backend}'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.").
3. Implement tests in tests/T04_kernel/test_kernel_storage.py:
   - Add unit tests verifying:
     - make_storage returns SQLiteKernelStorage when SCP_STORAGE_BACKEND is unset or set to "sqlite" / "SQLITE".
     - make_storage raises NotImplementedError when SCP_STORAGE_BACKEND is set to "postgres", "mysql", etc.
     - make_storage docstring contains SPOF WARNING.
4. Run verification commands:
   - pytest tests/T04_kernel/test_kernel_storage.py -v
   - python tools/probe_gap05_occ_multiprocess.py
   - python tools/t00_meta_audit.py
5. Document all changes and exact command outputs in changes.md and handoff.md in c:\Users\check\Downloads\scp\.agents\worker_m1\.
6. Use send_message to report completion back to the parent orchestrator.
