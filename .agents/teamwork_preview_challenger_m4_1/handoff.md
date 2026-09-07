# BÁO CÁO BÀN GIAO KIỂM CHỨNG ĐỐI KHÁNG (HANDOFF REPORT)
## ADVERSARIAL CHALLENGE & VERIFICATION OF TASK KERNEL CONCURRENCY & DURABILITY

- **Bên bàn giao (Sender)**: `teamwork_preview_challenger_m4_1` (Vai trò: `critic`, `specialist`)
- **Bên nhận bàn giao (Recipient)**: Orchestrator / Parent Agent (`906356b8-83ad-47d8-a405-93dbb241fdf1`)
- **Phạm vi kiểm tra**: Đánh giá thực nghiệm các phát hiện về Task Kernel trong `DELTA_AUDIT_REPORT.md` và `probe_kernel_flaws.py`
- **Loại hình bàn giao**: Hard Handoff (Hoàn tất toàn bộ yêu cầu)

---

### 1. Quan sát thực tế (Observation)

1. **Quan sát mã nguồn `scp/task_kernel.py`**:
   - Dòng 158–160: Khai báo biến ngữ cảnh bộ nhớ RAM:
     ```python
     _LEASE_CONTEXT: ContextVar[dict[tuple[int, str], str]] = ContextVar(
         "scp_task_kernel_lease_context", default={}
     )
     ```
   - Dòng 169–170: Lấy `lease_id` từ bộ nhớ cục bộ của đối tượng:
     ```python
     def _bound_lease_id(kernel: Any, task_id: str) -> str | None:
         return _LEASE_CONTEXT.get().get((id(kernel), task_id))
     ```
   - Dòng 231–233: Bỏ qua kiểm tra lease khi `lease_id` không tồn tại trong RAM:
     ```python
     lease_id = _bound_lease_id(self, task_id)
     if not lease_id:
         return _original_transition(self, task_id, to_state, actor, reason, payload, event_id)
     ```

2. **Quan sát mã nguồn `scp/task_kernel_parts/taskkernel.py`**:
   - Dòng 114–148 (`TaskKernel.transition`): Phương thức gốc không nhận `lease_id` hay `expected_version`.
   - Dòng 142: Câu lệnh cập nhật SQL không có điều kiện bảo vệ:
     ```sql
     UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?
     ```

3. **Quan sát mã nguồn `scp/kernel_storage.py`**:
   - Dòng 103–109: Khởi tạo kết nối SQLite với cấu hình timeout:
     ```python
     conn = sqlite3.connect(
         self.db_path, timeout=10, isolation_level=None, check_same_thread=False
     )
     conn.execute("PRAGMA busy_timeout=10000")
     ```
   - Dòng 121–136: Vòng lặp retry 3 lần bắt ngoại lệ `OperationalError`.

4. **Kết quả thực thi lệnh kiểm thử terminal**:
   - Chạy `python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`:
     - Probe 1: Rogue Worker chiếm đoạt task thành công sang `HUMAN_REVIEW`, Worker hợp lệ crash với `InvalidTransition: HUMAN_REVIEW->VERIFYING`.
     - Probe 2: Worker mới vượt qua rào chắn `StaleLease` thành công và chuyển trạng thái sang `VERIFYING`.
     - Probe 3: Không có lỗi ném ra từ terminal trên Windows do độ trễ khởi động tiến trình con và cấu hình `busy_timeout=10000`.
     - Probe 4: Hai worker ghi đè mù quáng tăng version lên 3 mà không có lỗi xung đột.
   - Chạy `python .agents/teamwork_preview_challenger_m4_1/verify_kernel_stress.py`:
     - Test 1 (Multi-Process Lock Contention có Event đồng bộ): Process 2 chờ 0.975s và hoàn thành giao dịch thành công `('SUCCESS', 0.9751513004302979)`, không xuất hiện `database is locked`.
     - Test 2 (Multi-Thread Rogue Hijack): Rogue thread cướp quyền thành công, luồng chính crash `InvalidTransition`.
     - Test 3 (Multi-Process Rogue Hijack): Tiến trình con cướp quyền thành công `('SUCCESS', 'HUMAN_REVIEW')`, tiến trình chính crash `InvalidTransition`.
     - Chạy thử nghiệm giữ khóa 10.5 giây: Tiến trình đối thủ hoàn thành thành công sau 10.53s (`k2 succeeded in 10.53s`).

---

### 2. Chuỗi suy luận logic (Logic Chain)

1. Từ Quan sát 1 & 2: Vì `_bound_lease_id` phụ thuộc vào `id(kernel)` trong biến `ContextVar` cục bộ của tiến trình, bất kỳ worker nào chạy trên tiến trình khác (hoặc luồng khác không thừa kế context) đều nhận giá trị `lease_id = None`.
2. Từ dòng 233 (`if not lease_id: return _original_transition(...)`): Khi `lease_id` là `None`, TaskKernel tự động chuyển tiếp sang `_original_transition()` mà không hề kiểm tra xem task có đang được lease hay không.
3. Từ Quan sát 4 (Probe 1, Test 2, Test 3): Bất kỳ tác tử hay tiến trình nào cũng có thể gọi `transition()` để chuyển một task đang `RUNNING` sang `HUMAN_REVIEW` hoặc `CANCELLED`. Khi worker hợp lệ đã hoàn thành công việc và cố gắng chuyển trạng thái tiếp theo (`RUNNING -> VERIFYING`), nó bị crash vì trạng thái cơ sở dữ liệu đã bị cướp mất (`HUMAN_REVIEW -> VERIFYING` không hợp lệ). Điều này chứng minh lỗ hổng **Rogue Worker Hijack** là **CÓ THẬT VÀ TÁI LẬP 100%**.
4. Từ Quan sát 1 & 2 (Probe 2): Khi một lease hết hạn trên đồng hồ thực, chỉ tiến trình đã lưu lease trong `ContextVar` mới bị chặn bởi `_assert_lease`. Một tiến trình mới hoặc worker khởi động lại không có `lease_id` trong RAM, do đó hoàn toàn bỏ qua bước kiểm tra này và cập nhật trực tiếp vào cơ sở dữ liệu. Điều này chứng minh lỗ hổng **Stale Lease Bypass** là **CÓ THẬT VÀ TÁI LẬP 100%**.
5. Từ Quan sát 2 & 4 (Probe 4, Test 4): Câu lệnh `UPDATE tasks SET state=?, version=version+1 WHERE task_id=?` hoàn toàn thiếu mệnh đề `WHERE version = :expected_version`. Hai tiến trình cùng đọc dữ liệu ở phiên bản $V$ đều có thể ghi đè nối tiếp nhau, làm mất mát cập nhật (Lost Update) mà không hề có ngoại lệ OCC được kích hoạt.
6. Từ Quan sát 3 & 4 (Probe 3, Test 1, Thử nghiệm 10.5s): Nhận định của Explorer rằng "SQLite crash sau 300ms" là dựa trên phép tính số học sai lầm về sleep time mà bỏ qua `PRAGMA busy_timeout=10000`. SQLite trên thực tế chờ đợi tối đa hơn 30 giây trước khi báo lỗi. Do đó, tuyên bố về lỗi crash 300ms là một giả định sai trong harness của Explorer.

---

### 3. Các điểm lưu ý và giới hạn (Caveats)

- **Môi trường hệ điều hành Windows**: Trên Windows, cơ chế `spawn` của `multiprocessing` có độ trễ khởi tạo tiến trình ~0.5s, làm cho các kịch bản kiểm thử tranh chấp không đồng bộ (như Probe 3 của Explorer) dễ bị sai lệch nếu không dùng `Event` hoặc `Barrier` để khóa pha bắt đầu.
- **Phạm vi kiểm tra**: Challenger chỉ tập trung kiểm toán đối kháng 4 lỗ hổng của Task Kernel theo yêu cầu chỉ định (Lease Fencing, Rogue Hijack, Multi-process Concurrency, Optimistic Locking). Các phần khác như Policy PEP, PCController sandbox, và RealityJudge không nằm trong phạm vi phản biện của báo cáo này.

---

### 4. Kết luận (Conclusion)

- **Phán quyết (Verdict)**: **APPROVE (PHÊ DUYỆT BÁO CÁO CỦA WORKER M1-M3 CÓ HIỆU CHỈNH KỸ THUẬT)**.
- Toàn bộ các khiếm khuyết cốt lõi về **Rogue Worker Hijack**, **Stale Lease Bypass**, và **Missing Optimistic Lock** được chỉ ra trong `DELTA_AUDIT_REPORT.md` là **HOÀN TOÀN CHÍNH XÁC, NGUY CƠ CAO (CRITICAL) VÀ CẦN PHẢI NÂNG CẤP TRIỆT ĐỂ Ở CẤP ĐỘ CƠ SỞ DỮ LIỆU**.
- Cần hiệu chỉnh lại tài liệu để đính chính cơ chế timeout thực tế của SQLite (>30 giây thay vì 300ms).

---

### 5. Phương pháp xác minh độc lập (Verification Method)

Bất kỳ kiểm toán viên nào cũng có thể tự tái lập độc lập bằng các bước sau:

1. Chạy kịch bản nguyên bản của Explorer:
   ```powershell
   python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py
   ```
   Quan sát đầu ra của PROBE 1, PROBE 2 và PROBE 4 để thấy lỗi `InvalidTransition` và cướp quyền trực tiếp.

2. Chạy kịch bản đối kháng có đồng bộ hóa của Challenger:
   ```powershell
   python .agents/teamwork_preview_challenger_m4_1/verify_kernel_stress.py
   ```
   Xác minh rằng:
   - TEST 1 chứng minh SQLite không crash sau 300ms mà chờ đợi thành công (`SUCCESS`).
   - TEST 2 & TEST 3 chứng minh `_LEASE_CONTEXT` hoàn toàn bất lực trước đa luồng và đa tiến trình.
   - TEST 4 chứng minh việc tăng version mù quáng cho phép ghi đè giao dịch song song.
