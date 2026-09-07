# DISPATCH — teamwork_preview_swe_2

## Mission
Vá Tử huyệt số 3 và 4 (GAP-03 + GAP-04) trong `scp/task_kernel_parts/taskkernel.py` theo đúng quy trình Zero-Trust với đầy đủ Adversarial Review.

## Working Directory
`c:\Users\check\Downloads\scp\.agents\teamwork_preview_swe_2`

## Source of Truth
- Authoritative User Request: `c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md` (entry 2026-09-07T01:56:25Z)
- Core Rules & Invariants: `c:\Users\check\Downloads\scp\.agents\AGENTS.md`, `c:\Users\check\Downloads\scp\GA.md`
- SCP DNA: `c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md`

## Mandatory Binding
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## Target Details
- Target file: `scp/task_kernel_parts/taskkernel.py`
- Target function: `rebuild_projection()` (around lines ~1198-1205)
- GAP-03: Blind Version Increment (CRITICAL) — `WHERE task_id=?` thiếu `AND version=?`. Thêm `AND version=?`, kiểm tra `cur.rowcount == 1`, raise `OptimisticLockError` nếu fail. Phải query version hiện tại trước để so khớp.
- GAP-04: rebuild_projection Transaction Boundary (HIGH) — Kiểm tra xem `rebuild_projection()` có được bao bọc đúng trong transaction (`self._begin()` / `self._commit()`) chưa. Nếu chưa, bọc toàn bộ hàm trong transaction.

## Acceptance Criteria
- [ ] Thiết kế và chạy Probe Script FA-09: Chứng minh hai luồng có thể ghi đè nhau — Probe phải Đỏ (RED) trước khi sửa.
- [ ] Anti-Placebo Mutation Test: Code buggy → Probe RED. Code đã sửa → Probe GREEN.
- [ ] `pytest tests/ -q` ≥ 430 PASS, exit=0.
- [ ] `python tools/t00_meta_audit.py` PASS.
- [ ] Handoff report gồm: HEAD_SHA, TREE_HASH, WORKTREE, Python/SQLite version.

## 2026-09-07T01:57:13Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are teamwork_preview_swe_2, the SWE Light Orchestrator for this task.
Your working directory is: c:\Users\check\Downloads\scp\.agents\teamwork_preview_swe_2
All agent metadata, plans, progress, and handoffs must reside within your working directory.

Read your dispatch file at: c:\Users\check\Downloads\scp\.agents\teamwork_preview_swe_2\DISPATCH.md
Read the authoritative user request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (entry 2026-09-07T01:56:25Z)
Pre-session mandate: Read GA.md and load scp-dna from .agents/skills/scp-dna/SKILL.md before any action.

Task:
Vá Tử huyệt số 3 và 4 (GAP-03 + GAP-04) trong `scp/task_kernel_parts/taskkernel.py` theo đúng quy trình Zero-Trust với đầy đủ Adversarial Review (SWE Light loop: implementer -> reviewer rounds).

Target details:
- Target file: `scp/task_kernel_parts/taskkernel.py`
- Target function: `rebuild_projection()` (around lines ~1198-1205)
- GAP-03: Blind Version Increment (CRITICAL) — `WHERE task_id=?` thiếu `AND version=?`. Thêm `AND version=?`, kiểm tra `cur.rowcount == 1`, raise `OptimisticLockError` nếu fail. (Lưu ý: phải query `version` hiện tại trước để so khớp).
- GAP-04: rebuild_projection Transaction Boundary (HIGH) — Kiểm tra xem `rebuild_projection()` có được bao bọc đúng trong transaction (`self._begin()` / `self._commit()`) chưa. Nếu chưa: Bọc toàn bộ hàm trong transaction.

Acceptance Criteria:
- [ ] Thiết kế và chạy Probe Script FA-09: Chứng minh hai luồng có thể ghi đè nhau — Probe phải Đỏ (RED) trước khi sửa.
- [ ] Anti-Placebo Mutation Test: Code buggy → Probe RED. Code đã sửa → Probe GREEN.
- [ ] `pytest tests/ -q` ≥ 430 PASS, exit=0.
- [ ] `python tools/t00_meta_audit.py` PASS.
- [ ] Handoff report trong working directory gồm: HEAD_SHA, TREE_HASH, WORKTREE, Python/SQLite version.

When work is completed, deliver your final handoff report and notify Sentinel via send_message.
