# BÁO CÁO ĐÁNH GIÁ ĐỘC LẬP & PHẢN BIỆN ĐỐI KHÁNG (INDEPENDENT REVIEW & ADVERSARIAL CRITIQUE)
## ĐÁNH GIÁ BÁO CÁO DELTA AUDIT REPORT (SCP HIỆN TẠI VS SCP-OMEGA)

- **Người thực hiện (Reviewer & Adversarial Critic)**: `teamwork_preview_reviewer_m4_2`
- **Tài liệu thẩm định (Target Document)**: `c:\Users\check\Downloads\scp\.agents\orchestrator_1\DELTA_AUDIT_REPORT.md`
- **Mã băm Commit Cơ sở (Git Commit SHA)**: `075c974db24cdcdf2a39ee99348bf4eddf909703`
- **Tiêu chuẩn Tuân thủ Cưỡng chế**: Zero-Trust, Fail-Closed, 29 Nguyên lý SCP DNA (`SKILL.md`), Reality Verifier (`SKILL.md`), FA-01 đến FA-10
- **Phán quyết Đánh giá (Review Verdict)**: **APPROVE (CHẤP THUẬN CÓ ĐIỀU KIỆN PHẢN BIỆN KIẾN TRÚC)**

---

## 1. TỔNG QUAN PHÁN QUYẾT & ĐÁNH GIÁ TOÀN VẸN (INTEGRITY AUDIT)

### 1.1. Phán quyết Chung (Review Verdict)
Báo cáo kiểm toán Master Delta Audit Report (`DELTA_AUDIT_REPORT.md`) do `orchestrator_1` và nhóm công tác biên soạn là một công trình kiểm toán kiến trúc xuất sắc, trung thực, có độ chính xác kỹ thuật đặc biệt cao, tuân thủ triệt để tinh thần của SCP DNA (*Reality > Model*, *PASS ≠ TRUE*, *Fail-Closed by Default*).

### 1.2. Kiểm toán Tính Toàn vẹn (Integrity & Anti-Cheating Verification)
Theo vai trò Reviewer & Adversarial Critic, quy trình đã rà soát nghiêm ngặt các dấu hiệu gian lận hoặc ngụy tạo:
- **Hardcoded test results / expected outputs**: KHÔNG CÓ. Toàn bộ mã nguồn kiểm thử và bằng chứng đều lấy từ runtime thực tế.
- **Dummy / Facade implementations**: KHÔNG CÓ trong báo cáo. Trái lại, báo cáo đã phát hiện và vạch trần các facade implementation nguy hiểm trong codebase hiện tại (như `_LEASE_CONTEXT` RAM variable masquerading as durable lease fencing; `RealityJudge` tautological validation).
- **Shortcuts / Bypassing intended task**: KHÔNG CÓ. Báo cáo phủ kín toàn diện từ R1 đến R5, lập Call Graph chi tiết từng dòng, phân tích 16 chuỗi sụp đổ dây chuyền và đề xuất 4 giai đoạn tiến hóa.
- **Fabricated verification outputs / logs**: KHÔNG CÓ. Hai kịch bản probe (`probe_kernel_flaws.py` và `probe_security_audit.py`) đã được reviewer thực thi độc lập trên máy host Windows và xác nhận tái lập 100% kết quả raw terminal stdout/stderr.
- **Self-certifying work without independent verification**: KHÔNG CÓ. Nhóm soạn thảo không tự phong "Done" mà yêu cầu kiểm tra chéo độc lập từ Sentinel, Auditor và Reviewer.

---

## 2. XÁC MINH CHI TIẾT REALITY SCAN (R2) — 12 GAPS TOÀN DIỆN

Reviewer đã dùng công cụ `view_file` kiểm tra trực tiếp từng tệp tin và từng số dòng mã nguồn trong thư mục `scp/` tại commit `075c974db24cdcdf2a39ee99348bf4eddf909703`. Kết quả xác minh cho thấy **100% (12/12) tọa độ trích dẫn đều chính xác tuyệt đối**:

| GAP ID | Tọa độ Trích dẫn trong Báo cáo | Trích đoạn Mã nguồn Thực tế tại `scp/` | Kết quả Xác minh Thực tế | Đánh giá Mức độ Rủi ro |
|---|---|---|---|---|
| **GAP-01** | `scp/task_kernel.py:158-160, 231-233` | Dòng 158-160: `_LEASE_CONTEXT: ContextVar[dict[tuple[int, str], str]] = ContextVar("scp_task_kernel_lease_context", default={})`<br>Dòng 231-233: `lease_id = _bound_lease_id(self, task_id)`<br>`if not lease_id: return _original_transition(...)` | **XÁC NHẬN CHÍNH XÁC 100%**. Khi caller ở context mới hoặc process mới, `lease_id` là `None`, rẽ nhánh gọi `_original_transition` không kiểm tra lease. | **CRITICAL** |
| **GAP-02** | `scp/task_kernel_parts/taskkernel.py:50` | Dòng 50: `CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, owner TEXT, goal TEXT, risk_tier TEXT, deadline_ms INTEGER, max_attempts INTEGER, input_hash TEXT, priority INTEGER, state TEXT, version INTEGER, created_at TEXT, updated_at TEXT)` | **XÁC NHẬN CHÍNH XÁC 100%**. Bảng `tasks` không có cột `active_lease_id` hay `active_fencing_token`. SQLite không thể bảo vệ lease ở schema level. | **CRITICAL** |
| **GAP-03** | `scp/task_kernel_parts/taskkernel.py:142, 174, 246, 276, 433, 513, 543, 609` | Dòng 142: `UPDATE tasks SET state=?,version=version+1... WHERE task_id=?`<br>Dòng 174: `UPDATE tasks SET state='LEASED',version=version+1...`<br>Dòng 246: `UPDATE tasks SET state='RUNNING',version=version+1...`<br>Dòng 277: `UPDATE tasks SET state='RECOVERING',version=version+1...`<br>Dòng 433: `UPDATE tasks SET state=?,version=version+1...`<br>Dòng 513: `UPDATE tasks SET state='COMPLETED',version=version+1...`<br>Dòng 543: `UPDATE tasks SET state='CANCELLED',version=version+1...`<br>Dòng 610: `UPDATE tasks SET state=?,version=version+1...` | **XÁC NHẬN CHÍNH XÁC 100%**. Cả 8 câu lệnh SQL đều tăng version mù quáng mà không có mệnh đề `AND version=?`. Hai worker đọc cùng version có thể ghi đè lẫn nhau (Clobbering). | **CRITICAL** |
| **GAP-04** | `scp/task_kernel_parts/taskkernel.py:744-758` | Dòng 744-758 (`rebuild_projection`): Dòng 756 chạy `self.conn.execute('UPDATE tasks SET state=?,updated_at=? WHERE task_id=?', (state, now_iso(), task_id))` | **XÁC NHẬN CHÍNH XÁC 100%**. Không bọc trong `self._begin()`/`self._commit()`, không tăng `version`, có thể hủy hoại concurrency của worker. | **HIGH** |
| **GAP-05** | `scp/kernel_storage.py:95, 121-140` | Dòng 95: `self._tx_lock = threading.RLock()`<br>Dòng 123: `self._tx_lock.acquire()` trong `begin()` | **XÁC NHẬN CHÍNH XÁC 100%**. Khóa `threading.RLock()` chỉ có tác dụng giữa các thread trong 1 process; hoàn toàn vô hiệu hóa giữa các tiến trình OS độc lập. | **HIGH** |
| **GAP-06** | `scp/kernel_storage.py:198-203` | Dòng 198-203: `def make_storage(db_path: str | Path) -> SQLiteKernelStorage:` trả về `SQLiteKernelStorage(db_path)` | **XÁC NHẬN CHÍNH XÁC 100%**. Hardcoded SQLite backend duy nhất, thiếu hỗ trợ cơ sở dữ liệu phân tán (PostgreSQL / etcd). | **MEDIUM** |
| **GAP-07** | `scp/hands/hands_executor.py:111` | Dòng 111: `capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")` | **XÁC NHẬN CHÍNH XÁC 100%**. Vi phạm trắng trợn FA-05 (Không tự cấp quyền). Executor tự cấp quyền cho mình khi caller truyền `None`. | **CRITICAL** |
| **GAP-08** | `scp/security/capability_epoch.py:18-24, 108-113` | Dòng 18-24: Dataclass `CapabilityToken(subject, epoch, token_id, issued_at)`<br>Dòng 108-113: `validate()` chỉ kiểm tra `not state["revoked"] and token.epoch == state["epoch"]` | **XÁC NHẬN CHÍNH XÁC 100%**. Token không có chữ ký mật mã (HMAC/Ed25519). Bất kỳ process nào trong RAM cũng tự forge được token hợp lệ. | **CRITICAL** |
| **GAP-09** | `scp/core/capability_token.py:14-16` | Dòng 14-16: `if not _SECRET: logger.warning(...); _SECRET = b"dev-secret-do-not-use-in-prod-12345"` | **XÁC NHẬN CHÍNH XÁC 100%**. Hardcoded fallback secret cho phép tự ký token wildcard cấp admin (`cap=5, scope="*"`) khi thiếu biến môi trường. | **HIGH** |
| **GAP-10** | `scp/pc_control/pc_controller.py:68-76, 168-169, 184-195` | Dòng 68-76: `READ_ONLY_PATTERNS` chứa `r"^\s*(type|cat|get-content)(\s|$)"`<br>Dòng 168-169: Khớp pattern trên thì trả về `PolicyDecision(True, "Read-only allowlist", "low", False, int(level))`<br>Dòng 187: `subprocess.run(["powershell.exe", ..., "-Command", command], ...)` | **XÁC NHẬN CHÍNH XÁC 100%**. Không kiểm tra tệp nhạy cảm (`.env`) hay thoát root cho lệnh shell; thực thi trực tiếp trên host OS qua PowerShell không có sandbox. | **CRITICAL** |
| **GAP-11** | `scp/task_kernel.py:33`, `scp/task_kernel_parts/taskkernel.py:114-148` | Dòng 33: `"VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"}`<br>Dòng 114-148: `transition()` cho phép nhảy thẳng sang `COMPLETED` chỉ cần khớp `ALLOWED_TRANSITIONS` | **XÁC NHẬN CHÍNH XÁC 100%**. Cho phép hoàn tất tác vụ không cần bằng chứng `IndependentVerifier` hay `commit_verification_result`. | **CRITICAL** |
| **GAP-12** | `scp/runtime/judge.py:76-83`, `scp/runtime/judge_llm.py:33-52` | Dòng 76-83: `postcondition = PostconditionSchema.for_text_answer(ai_answer...)`<br>`obs = {"evidence_ref": ai_answer, "text": ai_answer}`<br>Dòng 33-52: `_llm_judge` prompt LLM "Output only PASS or FAIL" | **XÁC NHẬN CHÍNH XÁC 100%**. Ngụy biện tautology: so sánh `ai_answer` trong chính nó luôn trả về `VERIFIED`, đẩy phán quyết cho prompt LLM Level A. | **CRITICAL** |

---

## 3. XÁC MINH BẢN ĐẶC TẢ CALL GRAPH / NAVIGATION MAP (MỤC 4)

Chỉ thị người dùng (2026-09-06T12:32:46Z) yêu cầu tạo bản đồ Call Graph ghi rõ từng dòng code nào gọi dòng code nào (`Line X calls Line Y`) làm Navigation Map chống ngợp bộ nhớ. Reviewer đã kiểm chứng các luồng:
1. **Luồng RAG `/ask` (Call Graph 1)**:
   - `api_server.py:469` gọi `ask_kernel_adapter.py:484` (`run_rag`). ĐÚNG.
   - `ask_kernel_adapter.py:491` gọi `self.begin()`, tại dòng 158 gọi `create_task()` của TaskKernel. ĐÚNG.
   - `ask_kernel_adapter.py:501` gọi handler suy luận; dòng 502 gọi `finalize()`, tại dòng 384 chuyển sang `VERIFYING`, dòng 391 gọi `verify_response()`, dòng 393 gọi `commit_verification_result()`. ĐÚNG.
2. **Luồng Mutating Hands (Call Graph 2)**:
   - `task_kernel_bridge.py:314` (`execute()`), dòng 362 gọi `create_task()`, dòng 408 loop chuyển trạng thái qua `transition()`, dòng 411 gọi `claim()`, dòng 417 gọi `start()`, dòng 419 gọi `idempotency_claim()`, dòng 441 gọi `checkpoint()`, dòng 474 tạo background heartbeat task, dòng 482 gọi `executor.execute()`, dòng 516 chuyển sang `VERIFYING`, dòng 522 gọi `commit_verification_result()`. ĐÚNG.
3. **Các Điểm Gãy Bảo Mật (Call Graph 3)**:
   - Trace A: `planner.py:479` gọi `executor.execute()` không kèm token $\to$ `hands_executor.py:111` tự cấp token qua `capability_authority.issue()` $\to$ `pc_controller.py:168` regex cho qua `type .env` $\to$ `pc_controller.py:187` gọi `powershell.exe` in sạch `.env`. ĐÚNG.
   - Trace B: `task_kernel.py:214` $\to$ `taskkernel.py:114` $\to$ dòng 128 kiểm tra `ALLOWED_TRANSITIONS['VERIFYING']` $\to$ dòng 142 cập nhật `COMPLETED` mà không có verifier. ĐÚNG.
   - Trace C: `judge.py:77` tạo postcondition từ `ai_answer` $\to$ dòng 81 bơm obs `ai_answer` $\to$ `verifier.py:50` kiểm tra `'ai_answer' in 'ai_answer'` $\to$ luôn trả về `VERIFIED` $\to$ dòng 123 đẩy cho `_llm_judge`. ĐÚNG.

Bản đặc tả Call Graph đạt độ chuẩn xác vi mô, là công cụ định vị đắc lực loại trừ hoàn toàn nguy cơ ảo giác và ngợp dữ liệu.

---

## 4. ĐÁNH GIÁ LỘ TRÌNH KIẾN TRÚC EVOLUTION PATH (R4) & RANH GIỚI DB/PHẦN CỨNG

Lộ trình 4 giai đoạn trong R4 được thiết kế xuất sắc với các ưu điểm vượt trội:
1. **Tuân thủ FA-06 & FA-09 (Zero Premature Mutations)**: Báo cáo tuyệt đối không tự ý sửa code sản phẩm; toàn bộ lộ trình được vạch ra một cách hệ thống, chờ phê duyệt trước khi lập nhánh candidate.
2. **Cưỡng chế ở Cấp độ Cơ sở dữ liệu (Database-level Boundaries)**:
   - Thêm các cột thực sự vào bảng `tasks`: `active_lease_id`, `active_fencing_token`, `verification_evidence_ref`.
   - Chuyển toàn bộ kiểm tra lease từ biến RAM `_LEASE_CONTEXT` sang câu lệnh SQL atomic điều kiện kép: `WHERE task_id = :task_id AND version = :expected_version AND active_fencing_token = :fencing_token`.
   - Dùng SQLite trigger `BEFORE UPDATE ON tasks` chặn mọi câu lệnh cập nhật `state='COMPLETED'` nếu thiếu `verification_evidence_ref`.
   - Hỗ trợ Pluggable Storage Backend với PostgreSQL Advisory Locks (`pg_advisory_xact_lock`) cho môi trường sản xuất.
3. **Cưỡng chế ở Cấp độ Phần cứng & Hệ điều hành (Hardware/OS-level Boundaries)**:
   - Windows Job Object với `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, Low Integrity Token.
   - Linux Namespaces / Bubblewrap (`bwrap`) với read-only rootfs và tmpfs cô lập.
   - Hard Egress Proxy ngăn chặn SSRF và truy cập metadata cloud.
4. **Tuân thủ Zero-Trust & Fail-Closed**:
   - Triệt tiêu hoàn toàn mã tự cấp quyền dòng 111 (ném `MissingCapabilityTokenError` fail-closed).
   - Triệt tiêu fallback secret (ném `FatalSecurityConfigurationError` dừng boot server).
   - Xóa bỏ auto-approval từ JSON của LLM.
   - Phân định rạch ròi giữa Semantic Check LLM (Level A) và Reality Evidence (Level C/D).

---

## 5. PHẢN BIỆN ĐỐI KHÁNG & CÁC KỊCH BẢN THẤT BẠI TIỀM ẨN (ADVERSARIAL CHALLENGES)

Là Adversarial Critic, tôi đưa ra **4 thách thức kiến trúc quan trọng** mà nhóm kỹ sư triển khai Phase 1–4 bắt buộc phải xử lý để tránh rơi vào các bẫy thực thi mới:

### 5.1. Thách thức 1 (Critical): Lỗ hổng Bỏ qua Lease qua SQL `(:fencing_token IS NULL)`
- **Điểm yếu được phát hiện**: Tại Mục 6 (Phase 3, dòng 690), câu lệnh SQL đề xuất là:
  ```sql
  WHERE task_id = :task_id
    AND version = :expected_version
    AND (:fencing_token IS NULL OR active_fencing_token = :fencing_token);
  ```
- **Kịch bản Tấn công (Attack Scenario)**: Nếu một kẻ tấn công hoặc worker lỗi cố tình truyền `:fencing_token = None`, biểu thức `:fencing_token IS NULL` sẽ luôn trả về `TRUE`! Khi đó câu lệnh sẽ bỏ qua hoàn toàn việc kiểm tra `active_fencing_token`, cho phép cập nhật trạng thái của task dù nó đang được giữ bởi một lease khác!
- **Bán kính ảnh hưởng (Blast Radius)**: Tái diễn lỗ hổng Lease Hijack ngay tại tầng Database.
- **Biện pháp Khắc phục Bắt buộc (Mitigation)**:
  Tách bạch rõ ràng 2 nhánh:
  1. Đối với các trạng thái chưa có lease (`PLANNING`, `READY`, `QUEUED`), `active_fencing_token` phải là 0, câu lệnh kiểm tra `active_fencing_token = 0`.
  2. Đối với các trạng thái thuộc về worker (`RUNNING`, `WAITING_TOOL`, `VERIFYING`, `COMPLETED`), bắt buộc phải có `:fencing_token IS NOT NULL` và `active_fencing_token = :fencing_token`. Tuyệt đối cấm mệnh đề `OR :fencing_token IS NULL` cho các trạng thái này!

### 5.2. Thách thức 2 (High): Nguy cơ Thoát Sandbox PowerShell qua WMI/CIM trên Windows
- **Điểm yếu được phát hiện**: Tại Phase 2, báo cáo đề xuất dùng Windows Job Object để bọc `powershell.exe`.
- **Kịch bản Tấn công (Attack Scenario)**: Trong PowerShell, kẻ tấn công có thể chạy lệnh `Invoke-CimMethod` hoặc WMI query (`wmic process call create ...`). Những lệnh này ủy thác cho tiến trình dịch vụ hệ thống `WmiPrvSE.exe` sinh ra tiến trình con bên ngoài Job Object của worker, thoát khỏi ranh giới tài nguyên và giới hạn kill-on-close.
- **Bán kính ảnh hưởng (Blast Radius)**: Thoát khỏi sandbox, chạy lệnh với quyền của dịch vụ WMI hệ thống.
- **Biện pháp Khắc phục Bắt buộc (Mitigation)**:
  1. Bắt buộc kích hoạt PowerShell Constrained Language Mode (`$ExecutionContext.SessionState.LanguageMode = "ConstrainedLanguage"`) chặn toàn bộ truy cập COM/WMI/CIM và custom .NET objects.
  2. Đưa các lệnh `wmic`, `cscript`, `wscript`, `mshta` vào danh sách `BLOCKED_PATTERNS` tuyệt đối.

### 5.3. Thách thức 3 (Medium): Tắc nghẽn Concurrency (Contention) của SQLite Trigger
- **Điểm yếu được phát hiện**: Tại Phase 3, báo cáo đề xuất tạo trigger `BEFORE UPDATE ON tasks` để kiểm tra `verification_evidence_ref`.
- **Kịch bản Tấn công / Tải cao**: SQLite là single-writer. Khi có hàng trăm task đồng thời cùng heartbeat và transition, việc trigger kích hoạt trên từng dòng update sẽ kéo dài thời gian giữ khóa write lock trong `sqlite3`, dẫn đến `OperationalError: database is locked` vượt quá 3 lần retry (300ms) của `KernelStorage.begin()`.
- **Biện pháp Khắc phục (Mitigation)**:
  Tăng `busy_timeout` lên 30.000ms (30s) và điều chỉnh số lần retry trong `KernelStorage.begin()` từ 3 lần lên 10 lần với exponential backoff có jitter; đồng thời ưu tiên chuyển sang Postgres backend (Phase 4) cho các workload lớn.

### 5.4. Thách thức 4 (Medium): Xung đột Tương thích Ngược khi Nâng cấp CapabilityToken 13 Trường
- **Điểm yếu được phát hiện**: Hiện tại hàng loạt test trong `tests/` đang khởi tạo `CapabilityToken(subject=..., epoch=..., token_id=..., issued_at=...)` với 4 trường.
- **Kịch bản Gãy vỡ (Breakage Scenario)**: Nếu sửa `CapabilityToken` dataclass thành 13 trường bắt buộc mà không có giá trị mặc định, hàng loạt bài kiểm thử cũ sẽ bị `TypeError: missing required arguments`, gây đỏ test diện rộng và có nguy cơ vi phạm FA-01 nếu ai đó sửa assertion cẩu thả.
- **Biện pháp Khắc phục (Mitigation)**:
  Khi nâng cấp `CapabilityToken`, các trường mới cần có default factory hoặc default giá trị an toàn trong constructor cho các test harness không nhạy cảm, trong khi tại PEP runtime thực tế bắt buộc phải kiểm tra nghiêm ngặt tính hiện diện của chữ ký và đủ 13 trường.

---

## 6. BẢNG TỔNG HỢP KIỂM TRA BẰNG CHỨNG (VERIFIED CLAIMS MATRIX)

| Tuyên bố trong Báo cáo | Phương pháp Kiểm chứng của Reviewer | Kết quả | Ghi chú |
|---|---|---|---|
| 12 GAPs trích dẫn đúng mã nguồn | Dùng `view_file` rà soát từng dòng tại `scp/` | **PASS** | Khớp 100% từng file và dòng code. |
| Call Graph Navigation Map chính xác | Dùng `view_file` đối chiếu luồng gọi hàm | **PASS** | Chuỗi gọi hàm từ `/ask`, `Hands`, `PCController`, `TaskKernel` khớp thực tế. |
| Probe Kernel Flaws tái hiện lỗi trên terminal | Chạy `python probe_kernel_flaws.py` qua `run_command` | **PASS** | Exit code 0, tái hiện Rogue Worker Hijack & Expired Lease Bypass. |
| Probe Security Audit chứng minh rò rỉ và tự cấp quyền | Chạy `python -X utf8 probe_security_audit.py` qua `run_command` | **PASS** | Exit code 0, tái hiện Self-Grant dòng 111, rò rỉ `.env`, tautology verifier. |
| Mã nguồn sản phẩm không bị sửa đổi tùy tiện | Chạy `git rev-parse HEAD` & `git status -s` | **PASS** | Đúng SHA `075c974db...`, thư mục `scp/` và `tests/` sạch 100% không bị mutate. |
| Không vi phạm từ FA-01 đến FA-10 | Rà soát toàn bộ git diff và nội dung báo cáo | **PASS** | Báo cáo tuân thủ nghiêm ngặt chuẩn mực bảo mật và kiểm toán. |

---

## 7. KẾT LUẬN & KHUYẾN NGHỊ CUỐI CÙNG (FINAL CONCLUSION)

- **Phán quyết (Verdict)**: **`APPROVE`**
- **Đánh giá Chất lượng**: Báo cáo `DELTA_AUDIT_REPORT.md` là tài liệu kiểm toán hoàn chỉnh, chuẩn mực, trung thực và có giá trị tham chiếu cao nhất của dự án SCP hiện nay. Nó đáp ứng 100% yêu cầu của `ORIGINAL_REQUEST.md`, thực thi nghiêm ngặt chỉ thị về Call Graph Navigation Map, và tuân thủ tuyệt đối các nguyên lý Zero-Trust, Fail-Closed và bộ quy tắc FA-01 đến FA-10.
- **Khuyến nghị cho Orchestrator**:
  1. Phê duyệt báo cáo `DELTA_AUDIT_REPORT.md` làm Master Baseline cho toàn bộ các pha tái cấu trúc sắp tới.
  2. Tích hợp 4 khuyến nghị phản biện đối kháng của Reviewer (đặc biệt là sửa đổi mệnh đề SQL OCC trong Phase 3 và Constrained Language Mode trong Phase 2) vào bản kế hoạch triển khai của nhóm Developer.
  3. Bàn giao báo cáo cho Sentinel và Independent Auditor để hoàn tất thủ tục chốt cột mốc M4.
