# HANDOFF REPORT — Task Kernel Delta Audit Survey

- **Agent**: teamwork_preview_explorer_survey_1
- **Archetype**: explorer (Investigation / Synthesis)
- **Handoff Type**: Hard (Task Complete)
- **Target File**: `survey_kernel_report.md`

---

## 1. Observation (Quan sát Thực tế)

1. **Mã nguồn Task Kernel & In-Memory Lease Context**:
   - Tại `scp/task_kernel.py:158-160`:
     ```python
     _LEASE_CONTEXT: ContextVar[dict[tuple[int, str], str]] = ContextVar(
         "scp_task_kernel_lease_context", default={}
     )
     ```
   - Tại `scp/task_kernel.py:169-170`:
     ```python
     def _bound_lease_id(kernel: Any, task_id: str) -> str | None:
         return _LEASE_CONTEXT.get().get((id(kernel), task_id))
     ```
   - Tại `scp/task_kernel.py:231-233`:
     ```python
     lease_id = _bound_lease_id(self, task_id)
     if not lease_id:
         return _original_transition(self, task_id, to_state, actor, reason, payload, event_id)
     ```
   - Tại `scp/task_kernel_parts/taskkernel.py:114-148`:
     Phương thức `_original_transition` không hề nhận tham số `lease_id` hay `fencing_token`, không đọc bảng `leases`, và không kiểm tra bất kỳ quyền sở hữu lease nào trước khi chạy `UPDATE tasks SET state=?, version=version+1 ...`.

2. **Mã nguồn Database Schema**:
   - Tại `scp/task_kernel_parts/taskkernel.py:50`:
     ```sql
     CREATE TABLE IF NOT EXISTS tasks (
         task_id TEXT PRIMARY KEY,
         owner TEXT NOT NULL,
         goal TEXT NOT NULL,
         risk_tier TEXT NOT NULL,
         deadline_ms INTEGER NOT NULL,
         max_attempts INTEGER NOT NULL,
         input_hash TEXT NOT NULL,
         priority INTEGER NOT NULL DEFAULT 5,
         state TEXT NOT NULL,
         version INTEGER NOT NULL DEFAULT 1,
         created_at TEXT NOT NULL,
         updated_at TEXT NOT NULL
     );
     ```
     Bảng `tasks` không có cột `active_lease_id` hay `active_fencing_token`. Không có ràng buộc Database nào buộc một task ở trạng thái `LEASED` hoặc `RUNNING` phải có lease hợp lệ.

3. **Mã nguồn Storage & Concurrency**:
   - Tại `scp/kernel_storage.py:95`:
     `self._tx_lock = threading.RLock()`
     Khóa bảo vệ transaction là một in-process Python `RLock`, hoàn toàn vô hiệu hóa giữa các tiến trình hệ điều hành độc lập (multi-process workers).

4. **Kết quả Chạy Terminal Thực tế của Probe Script (FA-09)**:
   Lệnh thực thi:
   `python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`
   Kết quả output thực tế trên terminal:
   ```text
   ======================================================================
   PROBE 1: Rogue Worker Hijack via In-Memory _LEASE_CONTEXT Bypass
   ======================================================================
   [Worker A] Claimed lease lease_fb1450c29ef53060f9026716 (token=1).
   [Worker A] Current task state: RUNNING
   [Worker B] Connected to same database without lease.
   [Worker B] HIJACKED task-omega-1 to state: HUMAN_REVIEW
   [Worker A CRASHED] Legitimate worker failed with: InvalidTransition: HUMAN_REVIEW->VERIFYING

   ======================================================================
   PROBE 2: Expired Lease Bypass via Fresh Context (Unfenced Transition)
   ======================================================================
   [k1] Task started with 1.0s TTL lease (token=1).
   [k1] 1.2 seconds elapsed. Lease has expired on wall-clock.
   [k1 correctly blocked in memory] StaleLease: lease_0c0be40d66dd0ad95af372c9
   [k2 BYPASS SUCCESS] Task transitioned to: VERIFYING by unfenced_bypasser!

   ======================================================================
   PROBE 4: Missing Optimistic Lock (Blind Version Increment Overwrite)
   ======================================================================
   [Initial] Task created with version=1
   [After Worker 1] State: PLANNING, Version: 2
   [After Worker 2] State: CANCELLED, Version: 3
   [Vulnerability] Worker 2 blindly updated state without checking if version was still 1!
   ```

---

## 2. Logic Chain (Chuỗi Lập luận Suy luận)

1. **Từ Quan sát 1**: `_bound_lease_id` lưu trữ ánh xạ `(id(kernel), task_id) -> lease_id` trong một biến `ContextVar` của tiến trình Python.
2. **Suy ra**: Bất kỳ tiến trình nào khác, hoặc bất kỳ instance `TaskKernel` mới nào mở tệp database SQLite, đều có `_bound_lease_id == None`.
3. **Từ Quan sát 1 (tiếp)**: Dòng 231-233 chỉ định rằng nếu `not lease_id`, phương thức sẽ chuyển thẳng sang `_original_transition`.
4. **Suy ra**: Bất kỳ tiến trình nào không sở hữu lease đều có thể chuyển đổi trạng thái của bất kỳ task nào (kể cả task đang `RUNNING` dưới quyền của worker khác) mà không hề bị cản trở bởi cơ chế Fencing.
5. **Chứng minh thực tế từ Quan sát 4 (Probe 1 & Probe 2)**:
   - Worker B (không có lease) đã cướp quyền chuyển task đang chạy sang `HUMAN_REVIEW`, khiến Worker A (sở hữu lease hợp lệ) bị crash với lỗi `InvalidTransition: HUMAN_REVIEW->VERIFYING`.
   - Worker với lease đã hết hạn trong instance `k2` đã transition thành công task sang `VERIFYING` mà không bị ném `StaleLease`.
6. **Từ Quan sát 2 & Quan sát 4 (Probe 4)**: Vì bảng `tasks` không có điều kiện ràng buộc `WHERE version = :expected_version`, các lệnh cập nhật trạng thái diễn ra mù quáng, cho phép ghi đè trạng thái giữa các luồng chạy song song mà không có cơ chế phát hiện xung đột lạc quan (Optimistic Concurrency Control).
7. **Kết luận**: Ranh giới an toàn của Task Kernel hiện tại nằm ở biến RAM / ContextVar, hoàn toàn vi phạm nguyên tắc Zero-Trust, Fail-Closed và chỉ thị bắt buộc: "Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables."

---

## 3. Caveats (Các Điểm Giới hạn / Chưa Khảo sát)

1. **Phạm vi kiểm toán**:
   - Đã khảo sát toàn bộ `scp/task_kernel.py`, `scp/kernel_storage.py`, `scp/task_kernel_parts/taskkernel.py`, `scp/ask_kernel_adapter.py`, `scp/hands/task_kernel_bridge.py`.
   - Chưa đo lường benchmark độ trễ tải cao (stress test 500 concurrent workers) trên môi trường multi-container Docker thực tế (sẽ thực hiện ở các Wave kiểm thử tiếp theo).
2. **Giả định**:
   - Giả định rằng hệ điều hành Windows và POSIX đều cưỡng chế lock tệp SQLite theo cùng nguyên tắc WAL.

---

## 4. Conclusion (Kết luận Đánh giá Cuối cùng)

- **Trạng thái hệ thống**: **`KERNEL_PARTIAL` / `ORCHESTRATOR_ONLY`**.
- **Điểm nghẽn cốt lõi**: Cơ chế Lease Fencing và Transition Guard **đang dựa vào RAM (`_LEASE_CONTEXT`) thay vì Database Engine**. Điều này cho phép bất kỳ caller nào bypass Fencing và tạo ra các vụ crash dây chuyền hoặc lặp side effect trong môi trường đa worker.
- **Tính khả thi của SCP-Omega**: Hoàn toàn khả thi để nâng cấp lên chuẩn SCP-Omega bằng cách loại bỏ `_LEASE_CONTEXT`, đưa `active_fencing_token` vào schema bảng `tasks`, và bắt buộc mọi câu lệnh ghi phải có điều kiện nguyên tử `WHERE task_id=? AND version=? AND active_fencing_token=?`.

---

## 5. Verification Method (Phương pháp Kiểm chứng Độc lập)

Để độc lập tái hiện và kiểm chứng các quan sát và kết luận trên, người đánh giá có thể chạy trực tiếp:

1. **Chạy Probe Script độc lập**:
   ```bash
   python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py
   ```
   *Điều kiện xác nhận lỗi*:
   - Probe 1 phải in ra dòng: `[Worker A CRASHED] Legitimate worker failed with: InvalidTransition: HUMAN_REVIEW->VERIFYING`.
   - Probe 2 phải in ra dòng: `[k2 BYPASS SUCCESS] Task transitioned to: VERIFYING by unfenced_bypasser!`.

2. **Chạy toàn bộ bộ test Kernel hiện có để xác nhận tính toàn vẹn ban đầu**:
   ```bash
   pytest tests/T04_kernel/ -v
   ```

3. **Kiểm tra mã nguồn tại các dòng**:
   - `scp/task_kernel.py:158` (`_LEASE_CONTEXT`)
   - `scp/task_kernel.py:231-233` (Rẽ nhánh bypass lease khi `not lease_id`)
   - `scp/task_kernel_parts/taskkernel.py:142` (Update không có `WHERE version=?`)
