## 2026-09-06T15:38:00Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the Independent Post-Victory Auditor (teamwork_preview_victory_auditor).
Your assigned working directory is: c:\Users\check\Downloads\scp\.agents\victory_auditor_1\
Write your progress and report in c:\Users\check\Downloads\scp\.agents\victory_auditor_1\handoff.md.

<original_task>
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the SWE Light Orchestrator (`teamwork_preview_swe`).
Your working directory is: c:\Users\check\Downloads\scp\.agents\teamwork_preview_swe_1\
Original request path: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md

MISSION:
Thực thi Pha 1 của Kế hoạch Tiến hóa (Evolution Path) - Vá lỗ hổng GAP-01 (ContextVar Leak) được phát hiện trong báo cáo Delta Audit (`.agents/orchestrator_1/DELTA_AUDIT_REPORT.md`).

CONTEXT & BACKGROUND:
- Trước khi thực hiện, tham chiếu GA.md trên main, .agents/skills/scp-dna/SKILL.md, và .agents/skills/scp-task-kernel-review/SKILL.md.
- Lỗ hổng GAP-01: Trong file `scp/task_kernel.py` (quanh dòng 158-170 và 231-233), `ContextVar _LEASE_CONTEXT` bị rò rỉ hoặc cho phép bypass tầng kiểm tra Lease để nhảy vào `_original_transition`.
- Invariant INV-01: Atomic Fencing. Việc kiểm tra Lease phải được ràng buộc chặt chẽ với transaction của Database, không được phụ thuộc vào biến RAM in-memory dễ bị thao túng.
- File probe script tái hiện lỗi: `.agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`.
- Call Graph Navigation: Thiết lập Call Graph / Execution Trace chi tiết để điều hướng luồng kiểm toán và sửa đổi mà không bị quá tải bộ nhớ.

REQUIREMENTS:
1. Root Cause Resolution (GAP-01): Triệt tiêu hoàn toàn lỗ hổng rò rỉ bộ nhớ `ContextVar _LEASE_CONTEXT`. Đảm bảo không tiến trình nào có thể bypass lớp kiểm tra Lease.
2. Invariant INV-01 (Atomic Fencing): Gắn chặt kiểm tra Lease vào DB transaction.
3. Zero-Trust Compliance: Tuân thủ FA-01 đến FA-10. Sửa mã nguồn sản phẩm tại `scp/task_kernel.py` (và các file liên quan nếu cần), KHÔNG nới lỏng hay xóa test (FA-01, FA-02).
4. Run tests and produce terminal raw evidence:
   - Chạy `probe_kernel_flaws.py` (hoặc test tương đương) để chứng minh lỗ hổng đã được vá triệt để.
   - `pytest tests/` phải toàn bộ màu xanh PASS (không gây regression).
   - `python tools/t00_meta_audit.py` phải PASS (không có vi phạm FA).
5. Maintain progress.md and BRIEFING.md in your working directory (.agents/teamwork_preview_swe_1/).
6. When complete, generate handoff.md with full evidence and report completion.
</original_task>

<audit_instructions>
Conduct a rigorous, independent 3-phase post-victory audit:
- Phase 1: Timeline & provenance verification. Inspect git log, git status, and git diff.
- Phase 2: Cheating & regression detection across FA-01 to FA-10. Confirm no tests were deleted, skipped, or assertions weakened.
- Phase 3: Independent test execution:
  1. Run `python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`
  2. Run `pytest tests/T04_kernel/`
  3. Run `python tools/t00_meta_audit.py`
  4. Run full `pytest tests/`

Deliver a structured verdict (CONFIRMED or REJECTED) with full evidence and rationale to the parent orchestrator via send_message and handoff.md.
</audit_instructions>
