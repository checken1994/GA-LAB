## 2026-09-06T12:30:35Z

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

Original user request file: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Working directory: c:\Users\check\Downloads\scp\.agents\teamwork_preview_spec_miner_survey_1
Skills to read and apply:
- c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
- c:\Users\check\Downloads\scp\.agents\skills\scp-reality-verifier\SKILL.md

Mission / Task:
Mine and analyze authoritative target specifications in the repository:
- `spec/complete_scp_reference.yaml`
- `spec/protected_invariants.yaml`
- `spec/scp_future_target_manifest.yaml`
- `spec/scp_future_cause_effect_matrix.yaml`
- `spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json`
- `GA.md`
Specifically extract and define:
1. Target Manifest (R1): 3-4 core invariants mandatory in SCP-Omega (e.g., Invariant of Durable State & Lease Fencing, Invariant of External Zero-Trust & PEP Non-Bypassability, Invariant of Independent Reality Evidence, Invariant of Fail-Closed Cascading Recovery).
2. Formal definitions, mathematical/logical predicates, and preconditions/postconditions for these invariants.
3. Causal matrix dependencies: Map the cause-effect chains and identify what happens when an invariant fails (cascading failure modes for R3).
Write your findings to `c:\Users\check\Downloads\scp\.agents\teamwork_preview_spec_miner_survey_1\spec_mining_report.md` and your handoff to `c:\Users\check\Downloads\scp\.agents\teamwork_preview_spec_miner_survey_1\handoff.md`.
Update your progress.md regularly. When done, send a message to the orchestrator.

## 2026-09-06T12:33:17Z

**Context**: User Directive Update (2026-09-06T12:32:46Z) in ORIGINAL_REQUEST.md
**Content**: User yêu cầu bắt buộc: Để chống ngợp dữ liệu (context overload) khi audit, hãy tạo bản đặc tả chi tiết (Call Graph / Execution Trace) ghi rõ 'từng dòng code nào gọi dòng code nào' (line X calls line Y). Dùng phương pháp Call Graph này làm bản đồ định vị (Navigation Map) cốt lõi để theo dõi luồng xử lý mà không bị quá tải bộ nhớ.
**Action**: Trong báo cáo đặc tả (Spec Mining Report), tích hợp hướng dẫn cấu trúc Call Graph chuẩn cho SCP-Omega (chuỗi gọi hàm tương lai vs hiện tại) để đối chiếu trực tiếp với Call Graph từ mã nguồn thực tế.
