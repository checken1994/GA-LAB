# Dispatch Log — Orchestrator 2

## 2026-09-06T16:15:47Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are the Project Orchestrator for Phase 2 of the SCP Evolution Path.
Your working directory is: c:\Users\check\Downloads\scp\.agents\orchestrator_2
You must maintain plan.md, progress.md, and BRIEFING.md in your working directory.

Before performing code analysis or any technical actions:
1. Read GA.md on main.
2. Read the relevant skills:
   - c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
   - c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md
   - c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md
3. Review the original user request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
4. Call Graph Navigation: Establish a detailed line-by-line call graph / execution trace for kernel_storage.py and related DAOs to map out where UPDATEs occur.

MISSION & REQUIREMENTS:
Thực thi Pha 2 của Kế hoạch Tiến hóa (Evolution Path) - Tiêu diệt Tử huyệt số 2 (GAP-02: OCC Blind Overwrites).

Working directory: c:\Users\check\Downloads\scp
Integrity mode: benchmark

### R1. Root Cause Resolution (GAP-02)
Ở Pha 1, chúng ta đã bít lỗ hổng OCC cho bảng `tasks`. Tuy nhiên, Tử huyệt GAP-02 chỉ ra rằng hệ thống vẫn đang chịu rủi ro "Ghi đè mù" (Blind Overwrite) ở các bảng dữ liệu vệ tinh khác (như `artifacts`, `task_events`, `journals`, v.v.). Nhiệm vụ của đội là truy quét toàn bộ `scp/kernel_storage.py` và các DAO liên quan, đảm bảo MỌI lệnh `UPDATE` đều phải có mệnh đề `WHERE version=?`.

### R2. Áp dụng Invariant INV-01
Mọi thao tác cập nhật state phải trở thành Atomic. Bất kỳ lệnh cập nhật nào bị lệch version đều phải văng lỗi `OptimisticLockError`.

### R3. Zero-Trust Compliance & Anti-Placebo
Tuyệt đối tuân thủ FA-01 đến FA-10. 
BẮT BUỘC thực hiện kiểm chứng đối chứng (Mutation Anti-Placebo) cho các kịch bản test.

## Acceptance Criteria
- [ ] Chạy thành công kịch bản mã độc/probe chứng minh hệ thống có thể bị ghi đè mù ở các bảng vệ tinh (FA-09 Exploit Mandate).
- [ ] Lệnh `pytest tests/ -q` trả về màu xanh (PASS).
- [ ] Script kiểm toán lõi `python tools/t00_meta_audit.py` phải PASS.
- [ ] Bằng chứng (Evidence) phải là log terminal thực tế.

Maintain coordination via progress.md and report completion when fully verified.
