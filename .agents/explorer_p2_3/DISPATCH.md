# Dispatch Log — Explorer P2-3 (FA-09 Exploit Mandate & Anti-Placebo Design)

## 2026-09-06T16:57:00Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

You are Explorer P2-3 (`teamwork_preview_explorer`).
Working directory: c:\Users\check\Downloads\scp\.agents\explorer_p2_3
Parent Orchestrator: orchestrator_3 (Conv ID: 4aab71c9-e6ee-472b-8c41-c64e48735a24)

Mandatory reading:
- c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md
- c:\Users\check\Downloads\scp\GA.md
- c:\Users\check\Downloads\scp\.agents\orchestrator_3\SCOPE.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-task-kernel-review\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

MISSION & FOCUS:
FA-09 Exploit Probe Design & Anti-Placebo Mutation Testing Strategy for GAP-02.
1. Review FA-09 Exploit Mandate:
   - "CẤM kết luận lỗi mà không có kịch bản chứng minh. Để claim một lỗi, BẮT BUỘC phải viết và chạy một script mô phỏng/tấn công độc lập. Nếu script không văng lỗi (Crash/Exception) trong thực tế terminal, giả thuyết lỗi đó phải bị loại bỏ."
2. Design a concrete, standalone Python exploit probe script:
   - What satellite table and operation will it target?
   - How will it demonstrate a blind overwrite (e.g. Worker A and Worker B read same record at version V; Worker A updates to V+1; Worker B blindly updates based on stale version, overwriting Worker A's changes without an error)?
   - How will it prove data loss / integrity violation under the current codebase?
   - How should the post-fix behavior differ (catching `OptimisticLockError` and preventing blind overwrite)?
3. Design Mutation Anti-Placebo tests:
   - Design tests that verify that if the `WHERE version=?` check is intentionally disabled or commented out, the tests FAIL.
   - Ensure the tests cannot pass by accident or via false confidence (anti-placebo).
4. Produce `analysis.md` and `handoff.md` in your working directory.
5. Report completion to parent.
