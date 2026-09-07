# HANDOFF REPORT: CAPABILITY SECURITY, SANDBOX BOUNDARIES & REALITY VERIFICATION

**Working Directory**: `c:\Users\check\Downloads\scp\.agents\teamwork_preview_explorer_survey_2`  
**Handoff Type**: Hard (Task Complete)  
**Recipient**: Parent / Orchestrator (`906356b8-83ad-47d8-a405-93dbb241fdf1`)  
**Mission**: Delta Audit of Capability Security, PEP/PDP, Sandbox Isolation, and Reality Verification against SCP-Omega target invariants.

---

## 1. Observation

1. **Capability Self-Granting (FA-05 Violation)**:
   - File `scp/hands/hands_executor.py`, dòng 110-111:
     ```python
     try:
         capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")
     ```
     Khi caller không cung cấp `capability_token`, `HandsExecutor` tự cấp token cho chính mình thông qua `self.capability_authority.issue()`.
2. **Unsigned Capability Token & Forgery**:
   - File `scp/security/capability_epoch.py`, dòng 18-24:
     ```python
     @dataclass(frozen=True)
     class CapabilityToken:
         subject: str
         epoch: int
         token_id: str
         issued_at: float
     ```
   - File `scp/security/capability_epoch.py`, dòng 108-113:
     ```python
     def validate(self, token: CapabilityToken | None) -> bool:
         if token is None:
             return False
         with self._lock:
             state = self._load()
             return not state["revoked"] and token.epoch == state["epoch"]
     ```
     Token là Python dataclass không chứa HMAC/asymmetric signature, không giới hạn công cụ (`tool`), đường dẫn tài nguyên (`resource`), hay thời gian hết hạn (`ttl`). Bất kỳ tiến trình nào trong RAM cũng có thể tự tạo instance `CapabilityToken(..., epoch=0)` và vượt qua hàm `validate()`.
3. **Hardcoded Fallback Secret**:
   - File `scp/core/capability_token.py`, dòng 14-16:
     ```python
     if not _SECRET:
         logger.warning("SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.")
         _SECRET = b"dev-secret-do-not-use-in-prod-12345"
     ```
     Bí mật fallback cố định cho phép kẻ tấn công tự sinh token HMAC hợp lệ với quyền admin (`cap=5`, `scope="*"`).
4. **PCController Sensitive Path Exfiltration & Sandbox Bypass**:
   - File `scp/pc_control/pc_controller.py`, dòng 68-76 (READ_ONLY_PATTERNS) và dòng 168-169:
     ```python
     if any(re.search(pattern, command, re.IGNORECASE) for pattern in self.READ_ONLY_PATTERNS):
         return PolicyDecision(True, "Read-only allowlist", "low", False, int(level))
     ```
   - File `scp/pc_control/pc_controller.py`, dòng 184-195 (`_run_sync`):
     ```python
     completed = subprocess.run(
         ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
         cwd=str(self.working_dir),
         ...
     ```
     Lệnh `type .env` hoặc `cat .env` được coi là `READ_ONLY` (Level 0, không cần approval). Hàm `execute()` không kiểm tra `_sensitive()` hoặc `_inside_root()`, thực thi trực tiếp trên máy host qua PowerShell, làm rò rỉ toàn bộ API key trong `.env` và các file ngoài workspace (ví dụ: `C:\Windows\win.ini`).
5. **TaskKernel Completion Gate Bypass**:
   - File `scp/task_kernel.py`, dòng 33 (`ALLOWED_TRANSITIONS`):
     ```python
     "VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"},
     ```
   - File `scp/task_kernel_parts/taskkernel.py`, dòng 114-148 (`transition`):
     Cho phép chuyển trạng thái thẳng sang `COMPLETED` mà không bắt buộc đi qua `commit_verification_result(task_id, lease_id, ...)` (dòng 496) và không đòi hỏi `evidence_ref` hay `verifier_verdict`.
6. **RealityJudge Tautology**:
   - File `scp/runtime/judge.py`, dòng 76-83:
     ```python
     if ai_answer:
         postcondition = PostconditionSchema.for_text_answer(ai_answer, evidence_required=False).to_dict()
     else:
         postcondition = PostconditionSchema.no_conditions().to_dict()
     obs = {"evidence_ref": ai_answer, "text": ai_answer}
     result = self.verifier.verify(postcondition, obs)
     ```
     Tạo postcondition `{"text_contains": ai_answer}` và so sánh với `obs["text"] = ai_answer`. Đây là một tautology toán học, luôn trả về `VERIFIED`. Sau đó, quyết định thực chất được giao cho `_llm_judge()` (hỏi LLM model "Output only PASS or FAIL"), biến Level A thành Level C giả tạo.
7. **Empirical Terminal Execution Result**:
   - Chạy lệnh `python -X utf8 .agents/teamwork_preview_explorer_survey_2/probe_security_audit.py` trả về exit code 0, in ra bằng chứng thực nghiệm rõ ràng:
     - Probe 1: Self-grant token thành công (`epoch: 0`), forged token được chấp nhận (`True`).
     - Probe 2: `read_file('.env')` bị chặn, nhưng `execute('type .env')` trả về returnCode 0 và dump mã nguồn `.env`; đọc `C:\Windows\win.ini` thành công.
     - Probe 3: Chuyển thẳng task từ `VERIFYING` sang `COMPLETED` mà không cần verifier.
     - Probe 4: `IndependentVerifier` trả về `VERIFIED` cho postcondition tautology của câu trả lời giả mạo.

---

## 2. Logic Chain

1. **Từ Observation 1 & 2**: Vì `HandsExecutor` tự gọi `self.capability_authority.issue()` khi token vắng mặt, hệ thống vi phạm trực tiếp nguyên tắc Zero-Trust và điều cấm FA-05 (No self-granting authority). Kết hợp với việc `CapabilityToken` chỉ là một dataclass RAM không chữ ký, một kẻ tấn công hoặc agent con có thể tự tạo bất kỳ token nào để vượt qua PEP.
2. **Từ Observation 3**: Do có fallback secret cố định trong `scp/core/capability_token.py`, tính bất biến mật mã (cryptographic integrity) bị phá vỡ hoàn toàn nếu môi trường không cấu hình secret.
3. **Từ Observation 4**: Mặc dù `PCController` có logic `_sensitive` để bảo vệ `.env`, nó chỉ được gắn vào hàm `read_file()`. Do regex `READ_ONLY_PATTERNS` trong hàm `evaluate()` xem `type` và `cat` là thao tác vô hại (level 0), bất kỳ tiến trình nào cũng có thể gọi `execute("type .env")` hoặc `execute("Get-Content C:\\...")` để lấy trích xuất dữ liệu nhạy cảm ngoài workspace mà không cần bất kỳ sự phê duyệt (approval) nào.
4. **Từ Observation 5**: Trong `TaskKernel`, phương thức an toàn `commit_verification_result()` tồn tại nhưng không phải là con đường độc quyền để hoàn tất task. Sự tồn tại của cạnh chuyển tiếp trực tiếp `VERIFYING -> COMPLETED` trong hàm `transition()` tạo ra một lỗ hổng bypass nghiêm trọng: bất kỳ worker nào cũng có thể tự claim là task đã `COMPLETED` mà không cần bất kỳ bằng chứng kiểm chứng thực tế nào từ `IndependentVerifier`.
5. **Từ Observation 6**: Khi `RealityJudge` sử dụng chính nội dung `ai_answer` để tạo postcondition `text_contains`, quá trình kiểm chứng của `IndependentVerifier` trở thành một phép đồng nhất thức (tautology) vô nghĩa. Khi đó, hệ thống phụ thuộc 100% vào prompt hỏi LLM (`_llm_judge`). Đây là lỗ hổng nghiêm trọng được định nghĩa trong `scp-reality-verifier`: lấy model self-reporting (Level A) đội lốt kiểm chứng hiện thực (Level C).
6. **Tổng hợp**: Hệ thống hiện tại vận hành trên nền tảng niềm tin biến RAM (in-memory variable trust), chưa đạt chuẩn Zero-Trust và chưa có các rào cản cưỡng chế ở cấp OS/Database/Hardware như yêu cầu của SCP-Omega.

---

## 3. Caveats

- **Phạm vi kiểm toán**: Đợt kiểm toán tập trung vào Capability Security, PEP/PDP, Sandbox Isolation, và Reality Verification. Các module khác như Vector DB RAG, Voice synthesizer hay Epistemic Knowledge Promotion chưa được phân tích sâu về logic nghiệp vụ nội bộ.
- **Môi trường Host**: Script probe được kiểm chứng trên môi trường Windows 11 host hiện tại. Trên Linux với Bubblewrap (`bwrap`), hành vi của `ProcessIsolationEnvironment` có sự khác biệt (sử dụng namespace), tuy nhiên `PCController` trên Linux vẫn dùng subprocess trực tiếp nếu không được định tuyến qua sandbox.
- **Giả định**: Báo cáo giả định rằng kẻ tấn công có khả năng tiêm mã (prompt injection) vào Planner hoặc có quyền gọi API/hàm cục bộ của Agent OS.

---

## 4. Conclusion

Kiến trúc hiện tại của SCP còn một khoảng cách đáng kể (delta gap) so với các định lý bất biến của SCP-Omega:
1. **Thiếu Capability Binding**: Token quyền lực chưa được bảo vệ bằng mật mã và bị self-grant tại Executor.
2. **Thiếu PEP nhất quán**: `PCController.execute()` là một lỗ hổng hở sườn nghiêm trọng làm vô hiệu hóa hàng rào bảo vệ tệp nhạy cảm.
3. **Thiếu Database Constraint cho Verification**: `TaskKernel` cho phép fake pass vào trạng thái `COMPLETED`.
4. **Ngụy biện Kiểm chứng Hiện thực**: `RealityJudge` che giấu Level A dưới vỏ bọc Level C.

Toàn bộ 4 lỗ hổng trên đã được chứng minh thực nghiệm thành công (FA-09) và kế hoạch nâng cấp kiến trúc 4 giai đoạn đã được đề xuất chi tiết trong `survey_security_report.md`.

---

## 5. Verification Method

Để độc lập tái lập và kiểm chứng các phát hiện trên:

1. **Chạy kịch bản khai thác độc lập (FA-09 Probe Script)**:
   ```powershell
   cd c:\Users\check\Downloads\scp
   python -X utf8 .agents/teamwork_preview_explorer_survey_2/probe_security_audit.py
   ```
   *Kỳ vọng*: Script chạy thành công với exit code 0, in ra xác nhận cả 4 PROBE đều CONFIRMED.
2. **Kiểm tra mã nguồn tại các tọa độ chỉ định**:
   - `scp/hands/hands_executor.py:111` (Self-grant token)
   - `scp/security/capability_epoch.py:108-113` (Validate không có chữ ký)
   - `scp/pc_control/pc_controller.py:168, 187` (Regex allowlist bypass và un-sandboxed PowerShell)
   - `scp/task_kernel_parts/taskkernel.py:128, 142` (Chuyển COMPLETED không qua verifier)
   - `scp/runtime/judge.py:77-83` (Tautology trong postcondition)
3. **Điều kiện vô hiệu hóa (Invalidation Conditions)**:
   Kết luận này chỉ bị vô hiệu hóa nếu có bằng chứng cho thấy `HandsExecutor` từ chối thực thi khi token bị thiếu, `PCController` chặn được `type .env`, `TaskKernel` chặn được `transition("COMPLETED")` khi thiếu bằng chứng, và `RealityJudge` không dùng `ai_answer` để kiểm chứng chính nó.

---
*Báo cáo Handoff hoàn thành.*
