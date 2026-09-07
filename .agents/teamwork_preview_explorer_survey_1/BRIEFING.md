# BRIEFING — 2026-09-06T12:36:00Z

## Mission
Investigate current SCP implementation of Task Kernel, State Machine, Locking, Concurrency, and Durability for Delta Audit.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1
- Original parent: 906356b8-83ad-47d8-a405-93dbb241fdf1
- Milestone: Delta Audit - Task Kernel Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify production code
- Bound by Zero-Trust and Fail-Closed principles
- Adhere to FA-01 through FA-10
- FORBIDDEN from self-granting authority or simulating PASS results
- Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables
- Output only to working directory c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1

## Current Parent
- Conversation ID: 906356b8-83ad-47d8-a405-93dbb241fdf1
- Updated: 2026-09-06T12:33:16Z (received call graph navigation map directive)

## Investigation State
- **Explored paths**:
  - `scp/task_kernel.py`, `scp/kernel_storage.py`, `scp/task_kernel_parts/taskkernel.py`
  - `scp/ask_kernel_adapter.py`, `scp/hands/task_kernel_bridge.py`, `scp/api_server.py`
  - `tests/T04_kernel/` (all 8 test files)
  - `data/hands/capability_state.json`, `scp/security/capability_epoch.py`
- **Key findings**:
  1. Lease Fencing is enforced in RAM via `_LEASE_CONTEXT: ContextVar` (`scp/task_kernel.py:158`).
  2. If `_bound_lease_id` is None, `_transition_fenced_by_bound_lease` falls back to `_original_transition`, completely bypassing lease checking.
  3. Rogue unleased worker can hijack running tasks to `HUMAN_REVIEW` or `CANCELLED`, causing legitimate workers to crash with `InvalidTransition`. Proven via terminal probe script.
  4. Stale/expired lease worker in a fresh instance can transition tasks without `StaleLease` being raised. Proven via terminal probe script.
  5. `tasks` schema lacks `active_lease_id` / `active_fencing_token` and `UPDATE tasks` lacks `WHERE version=?` optimistic concurrency control.
  6. Transaction locking uses in-process `threading.RLock()`; SQLite storage is a single-node SPOF without distributed consensus.
  7. Shared repo file `data/hands/capability_state.json` contains schema v2 while `capability_epoch.py` expects v1, causing capability revocation in tests relying on default data dir.
- **Unexplored areas**:
  - Multi-container distributed stress benchmarks.

## Key Decisions Made
- Created and executed reproducible probe script `probe_kernel_flaws.py` on terminal to satisfy FA-09.
- Generated detailed Call Graph Navigation Map (`line X calls line Y`) for `/ask` and Hands bridge.
- Produced comprehensive reports: `survey_kernel_report.md` and `handoff.md`.

## Artifact Index
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\DISPATCH.md` — Inbound dispatch instruction
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\BRIEFING.md` — Persistent awareness & state
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\progress.md` — Liveness heartbeat
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\probe_kernel_flaws.py` — FA-09 reproducible probe script
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\survey_kernel_report.md` — Full survey report
- `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\handoff.md` — 5-component handoff report
