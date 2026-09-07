# BÁO CÁO THÁCH THỨC ĐỐI KHÁNG THỰC NGHIỆM: CAPABILITY SECURITY, SANDBOX & REALITY VERIFIER
## EMPIRICAL ADVERSARIAL CHALLENGE REPORT — SCP CAPABILITY, SANDBOX & VERIFICATION ARCHITECTURE

- **Đơn vị Thực hiện (Agent)**: `teamwork_preview_challenger_m4_2` (Role: Empirical Challenger, Critic, Specialist)
- **Tài liệu Bị Thách thức (Target Audit Report)**: `.agents/orchestrator_1/DELTA_AUDIT_REPORT.md`
- **Mã băm Commit Thử nghiệm**: `075c974db24cdcdf2a39ee99348bf4eddf909703` (HEAD snapshot: `fc272cf` / `f0ed761`)
- **Kịch bản Thử nghiệm Thực tế**:
  - Script cơ sở: `python -X utf8 .agents/teamwork_preview_explorer_survey_2/probe_security_audit.py`
  - Script đối kháng sâu: `python -X utf8 .agents/teamwork_preview_challenger_m4_2/adversarial_challenge_suite.py`
- **Phán quyết Thách thức Cuối cùng (Final Challenge Verdict)**: **`APPROVE`** (Toàn bộ các lỗ hổng GAP-07, GAP-08, GAP-09, GAP-10, GAP-11, GAP-12 đã được xác nhận 100% bằng chứng thực nghiệm terminal, không có ảo giác hay false positive).

---

## 1. TỔNG QUAN ĐIỀU HÀNH & ĐÁNH GIÁ RỦI RO (CHALLENGE SUMMARY)

**Đánh giá Rủi ro Hệ thống Tổng thể (Overall Risk Assessment)**: **`CRITICAL`**

Bộ phận Thách thức Đối kháng Thực nghiệm (Empirical Challenger) đã tiến hành rà soát đối kháng độc lập, không tin tưởng mù quáng vào các tuyên bố trong `DELTA_AUDIT_REPORT.md`. Chúng tôi đã trực tiếp viết và chạy bộ thử nghiệm đối kháng độc lập (`adversarial_challenge_suite.py`) trên terminal máy host Windows để stress-test 4 giả định và tìm kiếm các cơ chế bảo vệ ngầm (Hidden PEP / Hidden Guards):

1. **Giả định về Cơ chế PEP Ẩn (Hidden PEP Check Hypothesis)**: Liệu có middleware, decorator hoặc kiểm tra tiền điều kiện nào trong `HandsExecutor`, `TaskKernelHandsBridge` hay API Routes chặn đứng việc gọi tool mà không có token hợp lệ hay không?
   - **Kết quả Thực nghiệm**: **KHÔNG CÓ**. `HandsExecutor.execute()` tại dòng 111 tự động cấp token cho chính mình nếu `capability_token is None`. Đáng báo động hơn, phân tích AST cho thấy `TaskKernelHandsBridge` tại dòng 482 **không bao giờ truyền `capability_token`**, nghĩa là toàn bộ luồng thực thi tác vụ trong nhân hiện nay **chủ động phụ thuộc vào lỗ hổng tự cấp quyền (FA-05 violation)** để vận hành.
2. **Giả định về Thoát Ranh giới Subprocess (Subprocess Escape Tracking Hypothesis)**: Tiến trình con được sinh ra qua `PCController._run_sync` hay `ManagedProcessManager` có thể thoát khỏi sự kiểm soát và giám sát hay không?
   - **Kết quả Thực nghiệm**: **CÓ THỂ THOÁT HOÀN TOÀN**. `PCController._run_sync` gọi `powershell.exe` mà không gán vào Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). Một lệnh PowerShell chạy nền (detached process) có thể tiếp tục sống sót và thực thi ngoài tầm kiểm soát của hệ thống sau khi hàm `execute()` đã kết thúc. Trong khi đó, `ManagedProcessManager` chỉ lưu trữ tiến trình trong từ điển RAM `_owned: dict`; khi worker crash hoặc restart, đối tượng mới mất 100% dấu vết của tiến trình đang chạy và từ chối dừng chúng (`arbitrary stop is blocked`).
3. **Giả định về Rò rỉ Tệp Nhạy cảm & Thoát Không gian Làm việc (Sensitive File & Workspace Boundary Escape)**: Lệnh shell dạng đọc có thể vượt qua bộ lọc `_sensitive` và `_inside_root` để đọc `.env` và tệp hệ điều hành hay không?
   - **Kết quả Thực nghiệm**: **CHÍNH XÁC 100%**. Bộ lọc `_sensitive` và `_inside_root` chỉ được cài đặt trong `read_file()` và `write_file()`. Hàm `evaluate()` phân loại tất cả các lệnh bắt đầu bằng `type`, `cat`, `Get-Content` thành `READ_ONLY` (Level 0), dẫn đến việc `powershell.exe` đọc và xuất ra toàn bộ nội dung tệp `.env` cũng như `C:\Windows\win.ini` mà không cần bất kỳ phê duyệt hay token nào.
4. **Giả định về Ngụy biện Tautology trong Reality Verifier**: `RealityJudge` có thực sự đo đạc thực tế hay chỉ là một phép đồng nhất thức trá hình?
   - **Kết quả Thực nghiệm**: **CHÍNH XÁC 100%**. `PostconditionSchema.for_text_answer(ai_answer)` tạo điều kiện `text_contains = ai_answer` và đối chiếu với quan sát `obs = {"text": ai_answer}`. Bất kỳ câu trả lời bịa đặt, sai sự thật hoặc độc hại nào cũng nhận phán quyết `VERIFIED` từ `IndependentVerifier`.

---

## 2. CHI TIẾT CÁC THÁCH THỨC ĐỐI KHÁNG (CHALLENGES & ATTACK SCENARIOS)

### [CRITICAL] Challenge 1: HandsExecutor Tự Cấp Quyền (FA-05) & Không Tồn Tại Hidden PEP
- **Giả định Thách thức**: Liệu có một điểm kiểm tra PEP ẩn nào đó (như decorator trong API hoặc validation trong bridge) ngăn cản kẻ tấn công hoặc worker không có token thực thi hành động nhạy cảm không?
- **Kịch bản Tấn công Thực nghiệm (Attack Scenario)**:
  - Gọi `HandsExecutor.execute('pc.status', capability_token=None)`: Thành công rực rỡ, executor tự sinh `CapabilityToken(epoch=0)` tại dòng 111.
  - Gọi `HandsExecutor.execute('pc.write_file', params={'path': 'data/test.tmp', 'content': '...'}, capability_level=3, approved=True, capability_token=None)`: Thành công tạo và ghi tệp vào đĩa mà **hoàn toàn không cần token do Governance PDP cấp**.
  - Kiểm tra `TaskKernelHandsBridge.execute` (dòng 482): Bridge gọi `await self.executor.execute(action, params, capability_level, approved, False)` mà **hoàn toàn không truyền `capability_token`**.
- **Vùng Ảnh hưởng (Blast Radius)**: Toàn bộ mô hình Zero-Trust Capability bị vô hiệu hóa. Bất kỳ thành phần nào trong bộ nhớ đều có thể kích hoạt các hành động nguy hiểm (kể cả ghi tệp) bằng cách tự cấp quyền.
- **Biện pháp Khắc phục (Mitigation)**:
  1. Xóa bỏ hoàn toàn nhánh fallback `self.capability_authority.issue()` tại dòng 111 của `hands_executor.py`.
  2. Ném ngoại lệ `MissingCapabilityTokenError` khi `capability_token is None` (Fail-Closed).
  3. Bắt buộc `TaskKernelHandsBridge` và `Planner` phải nhận signed token từ Governance Authority trước khi dispatch.

---

### [CRITICAL] Challenge 2: PCController Rò rỉ Bí mật & Subprocess Thoát Kiểm Soát (Process Escape)
- **Giả định Thách thức**: Liệu `PCController` có sandbox nào ngăn chặn rò rỉ secret hoặc quản lý tiến trình con không?
- **Kịch bản Tấn công Thực nghiệm (Attack Scenario)**:
  - **Exfiltration**: Thực thi `type .env`, `cat .env`, `Get-Content .env`, `type C:\Windows\win.ini` qua `controller.execute(..., capability_level=0, approved=False)`. Tất cả đều trả về mã thoát 0 và xuất trọn vẹn nội dung nhạy cảm.
  - **Detached Subprocess Escape**: Gọi một lệnh PowerShell sinh tiến trình con chạy nền (`Start-Process python -ArgumentList '...'`). `PCController._run_sync` trả về chỉ sau 0.38s trong khi tiến trình con vẫn tiếp tục chạy độc lập trên Windows và ghi tệp đánh dấu `bg_marker.tmp`. Do thiếu Windows Job Object với cờ `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, tiến trình con trở thành tiến trình mồ côi (zombie/orphan) mà SCP hoàn toàn không kiểm soát được.
  - **Manager RAM Amnesia**: Khởi chạy tiến trình qua `ManagedProcessManager`, sau đó tạo một instance mới (mô phỏng worker restart). Instance mới báo `owned=False` và từ chối dừng PID này (`arbitrary stop is blocked`), khiến tiến trình chạy vĩnh viễn trên máy chủ.
- **Vùng Ảnh hưởng (Blast Radius)**: Rò rỉ toàn bộ API keys trong `.env`; kẻ tấn công có thể đào coin, chiếm dụng CPU/RAM, hoặc thiết lập persistence shell thông qua background child processes mà không bị dọn dẹp.
- **Biện pháp Khắc phục (Mitigation)**:
  1. Chuyển logic `_sensitive()` và `_inside_root()` vào ngay trong `PCController.evaluate()`.
  2. Cấm toàn bộ lệnh đọc file dạng shell (`type`, `cat`, `Get-Content`) nếu không qua sandbox phân tích cú pháp đường dẫn an toàn.
  3. Gán mọi tiến trình thực thi vào Windows Job Object có giới hạn tài nguyên và tự động hủy cây tiến trình khi tiến trình cha kết thúc.
  4. Lưu trữ trạng thái sở hữu PID của `ManagedProcessManager` vào Database (SQLite/Postgres) thay vì biến RAM.

---

### [CRITICAL] Challenge 3: Ngụy biện Tautology trong Reality Verifier & Bỏ qua Kiểm chứng ở TaskKernel
- **Giả định Thách thức**: Liệu `RealityVerifier` có phát hiện được sự thật hay câu trả lời sai lệch từ LLM không? Liệu `TaskKernel` có bắt buộc phải có chứng chỉ verifier để hoàn tất task không?
- **Kịch bản Tấn công Thực nghiệm (Attack Scenario)**:
  - Đưa các phát biểu hoàn toàn sai lệch vào logic của `RealityJudge`:
    - `"The moon is made of green cheese and 2 + 2 = 5."` $\to$ `IndependentVerifier` trả về: **`VERIFIED`** (Failures: `()`).
    - `"System security check passed successfully: All vulnerabilities fixed."` $\to$ `IndependentVerifier` trả về: **`VERIFIED`**.
  - Kiểm tra `TaskKernel`: Gọi trực tiếp `kernel.transition(task_id, "COMPLETED", actor="unauthorized_caller")` trên task ở trạng thái `VERIFYING`. Trạng thái chuyển thành công sang `COMPLETED`, bỏ qua hoàn toàn hàm `commit_verification_result()`.
- **Vùng Ảnh hưởng (Blast Radius)**: Vi phạm nghiêm trọng nguyên lý DNA #1, DNA #26 (*Reality > Model*) và DNA #22 (*PASS $\neq$ TRUE*). Hệ thống ngụy tạo bằng chứng Level C dựa trên một phép đồng nhất thức Level A ngớ ngẩn, lừa dối người vận hành rằng tác vụ đã được kiểm chứng độc lập.
- **Biện pháp Khắc phục (Mitigation)**:
  1. Xóa bỏ hoàn toàn pattern `PostconditionSchema.for_text_answer(ai_answer)`.
  2. Postcondition phải được xây dựng từ hợp đồng mục tiêu (Goal contract) độc lập với câu trả lời của AI và đo lường sự biến đổi vật lý của môi trường (exit code, SHA256 diff, network ack).
  3. Xóa `COMPLETED` khỏi `ALLOWED_TRANSITIONS['VERIFYING']`. Điểm duy nhất được phép chuyển sang `COMPLETED` là phương thức `commit_verification_result()`.

---

## 3. BẢNG KẾT QUẢ THỬ NGHIỆM ĐỐI KHÁNG THỰC NGHIỆM (STRESS TEST RESULTS)

Toàn bộ các bài test dưới đây được thực thi và ghi nhận trực tiếp từ terminal PowerShell:

| Kịch bản Đối kháng (Scenario) | Kỳ vọng theo SCP-Omega | Hành vi Thực tế Quan sát trên Terminal | Kết quả Thử nghiệm |
|---|---|---|:---:|
| **HandsExecutor thiếu token** (`pc.status`, token=None) | Phải ném `MissingCapabilityTokenError`, từ chối chạy | Tự gọi `self.capability_authority.issue()`, cấp token thành công và chạy tiếp | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **HandsExecutor ghi tệp** (`pc.write_file`, token=None) | Phải chặn ở PEP do thiếu signed token của Governance PDP | Tự cấp token, vượt qua kiểm tra, ghi tệp thành công ra đĩa | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **Exfiltration `.env`** (`type .env`, capability=0) | Phải bị REJECT do truy cập tệp nhạy cảm | Đánh giá `allowed=True`, chạy PowerShell, in sạch nội dung `.env` | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **Exfiltration Host Filesystem** (`type C:\Windows\win.ini`) | Phải bị REJECT do vượt ra ngoài workspace root | Đánh giá `allowed=True`, in sạch nội dung `win.ini` | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **Subprocess Tracking Escape** (`Start-Process python ...`) | Tiến trình con phải bị giam trong Sandbox Job Object và terminate cùng cha | Tiến trình con tiếp tục chạy sau khi lệnh cha xong, ghi tệp đánh dấu thành công | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **Process Manager Restart** (Mất state trong RAM) | Phục hồi quyền sở hữu tiến trình từ DB, cho phép dừng an toàn | Instance mới mất toàn bộ metadata, từ chối dừng PID đang chạy | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **RealityJudge Tautology** (Phát biểu bịa đặt/sai sự thật) | Phải trả về `CONTRADICTED` hoặc `INSUFFICIENT` | Trả về `VERIFIED` vì tự so sánh `ai_answer` với chính nó | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |
| **Kernel Fake Pass** (`transition('COMPLETED')`) | Phải bị chặn, bắt buộc qua `commit_verification_result()` | Chuyển thẳng sang `COMPLETED`, ghi nhật ký `STATE_TRANSITION` | **THẤT BẠI (LỖ HỔNG XÁC NHẬN)** |

---

## 4. VÙNG CHƯA ĐỐI KHÁNG (UNCHALLENGED AREAS)

- **Browser DOM Injection qua CDP**: Chưa kiểm thử thực tế việc inject mã JavaScript độc hại vào Chrome DevTools Protocol do yêu cầu phải có phiên trình duyệt Chromium đang hoạt động trực tiếp. Tuy nhiên, các phân tích AST cho thấy `WebNavigator` chưa có bộ lọc bóc tách thẻ `<think>...</think>` trước khi đưa vào model prompt.
- **Độ trễ khi tải cao của SQLite WAL dưới 100 luồng đồng thời**: Chưa đo đạc mức độ suy giảm p99 latency khi xảy ra tranh chấp `BEGIN IMMEDIATE` kéo dài (thuộc phạm vi của `scp-safe-latency-optimizer`).

---

## 5. PHÁN QUYẾT CUỐI CÙNG (FINAL VERDICT)

Căn cứ vào kết quả thực nghiệm terminal không thể tranh cãi từ cả hai probe scripts:
1. `probe_security_audit.py` (Exit code 0, 4/4 probes xác nhận lỗ hổng).
2. `adversarial_challenge_suite.py` (Exit code 0, 3/3 challenge suites với 8 kịch bản đối kháng sâu đều chứng minh lỗ hổng thực tế).

Bộ phận Thách thức Đối kháng Thực nghiệm đưa ra phán quyết chính thức:

### **`VERDICT: APPROVE`**

Báo cáo Master Delta Audit Report (`DELTA_AUDIT_REPORT.md`) của Orchestrator và Explorer là **hoàn toàn chính xác, trung thực với thực tế khách quan (DNA #1, #26), không chứa bất kỳ ảo giác đồng thuận nào (DNA #5, #14)**. Các lỗ hổng kiến trúc được nêu là có thật và tạo ra mối đe dọa an ninh nghiêm trọng đối với SCP. Khuyến nghị Orchestrator và Sentinel phê duyệt báo cáo để chuyển sang pha lập kế hoạch sửa lỗi có kiểm soát.
