## 2026-09-06T17:51:29Z
MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You are Spec Miner 1 (spec_miner_invariants_1).
Your working directory is: c:\Users\check\Downloads\scp\.agents\spec_miner_invariants_1\
Read the authoritative request at: c:\Users\check\Downloads\scp\.agents\ORIGINAL_REQUEST.md (specifically timestamp ## 2026-09-06T17:49:43Z).

FORCED SKILL ACTIVATION:
You MUST use view_file to read directly:
1. c:\Users\check\Downloads\scp\.agents\skills\scp-delta-audit\SKILL.md
2. c:\Users\check\Downloads\scp\.agents\skills\scp-dna\SKILL.md
3. c:\Users\check\Downloads\scp\.agents\skills\scp-capability-security-review\SKILL.md

CALL GRAPH NAVIGATION MANDATE:
Khi thực hiện kiểm toán hoặc phân tích mã nguồn phức tạp, Agent BẮT BUỘC phải thiết lập bản đặc tả chi tiết "dòng code nào gọi dòng code nào" (Line-by-line Call Graph / Execution Trace). Dùng sơ đồ này làm bản đồ định vị (Navigation Map).

MISSION — PHASE 1 (TARGET MANIFEST), PHASE 3 (CAUSAL GAP ANALYSIS) & PHASE 5 (EVOLUTION PATH):
Target: `scp/hands/hands_executor.py` và cơ chế Cấp quyền (Authority/Capability).
Tử huyệt FA-05: Tự phong quyền (Self-granting authority) nếu Caller không cung cấp token.

Tasks:
1. Phase 1 — TARGET MANIFEST: Define 3-5 necessary invariants for HandsExecutor / Capability Authority:
   - For each invariant provide: ID, invariant statement, protected failure mode, observable evidence required to prove compliance, falsification condition.
2. Phase 3 — CAUSAL GAP ANALYSIS:
   - Create Mermaid causal graph with two paths: A. Current Implementation vs B. Required Invariant-Preserving Path.
   - For each gap: trigger → local failure → propagation → violated invariant → externally observable consequence.
   - Strictly separate CONFIRMED causal chains from HYPOTHETICAL causal chains.
3. Phase 5 — EVOLUTION PATH:
   - Formulate architectural evolution plan to eradicate self-granting authority, enforce Zero-Trust PEP at driver/execution boundary, rollback plan, compatibility considerations.
4. TUYỆT ĐỐI KHÔNG SỬA CODE SẢN PHẨM!
5. Write your comprehensive report to `c:\Users\check\Downloads\scp\.agents\spec_miner_invariants_1\target_manifest_and_gaps.md` and complete your handoff report `c:\Users\check\Downloads\scp\.agents\spec_miner_invariants_1\handoff.md`.
6. Send a message to orchestrator with summary and links when done.
