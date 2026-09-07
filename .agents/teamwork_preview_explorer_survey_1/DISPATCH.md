## 2026-09-06T12:30:35Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

Original user request file: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Working directory: c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1
Skills to read and apply:
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md

Mission / Task:
Investigate the current SCP implementation with respect to Task Kernel, State Machine, Locking, Concurrency, and Durability.
Specifically examine:
1. Where is Task State stored? Is it in-memory (RAM/variables, dictionaries) or durable in a database (SQLite, PostgreSQL, journal)?
2. How are State Transitions guarded? Are there atomic database locks, lease fencing tokens, or can multiple workers claim the same task / commit out-of-order?
3. Look at actual implementation files in `src/` (or wherever TaskKernel lives, e.g. `src/task_kernel/` or similar) and tests in `tests/T04_kernel/`.
4. Find exact locations of loose design, missing locks, race conditions, or in-memory bypasses.
5. Identify potential reproducible crash/exception/race condition targets for a probe script (FA-09).
Write your comprehensive report to `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\survey_kernel_report.md` and your handoff to `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_1\handoff.md`.
Update your progress.md regularly. When done, send a message to the orchestrator.

## 2026-09-06T12:33:16Z

**Context**: User Directive Update (2026-09-06T12:32:46Z) in ORIGINAL_REQUEST.md
**Content**: User yêu cầu bắt buộc: Để chống ngợp dữ liệu (context overload) khi audit, hãy tạo bản đặc tả chi tiết (Call Graph / Execution Trace) ghi rõ 'từng dòng code nào gọi dòng code nào' (line X calls line Y). Dùng phương pháp Call Graph này làm bản đồ định vị (Navigation Map) cốt lõi để theo dõi luồng xử lý mà không bị quá tải bộ nhớ.
**Action**: Khi phân tích mã nguồn Task Kernel / Concurrency / State Machine, bắt buộc trích xuất và trình bày Call Graph / Execution Trace chi tiết dạng `line X calls line Y` (FileA:LineX -> FileB:LineY) làm Navigation Map để chỉ ra chính xác vị trí thiếu lock, race condition, hoặc in-memory state bypass.
