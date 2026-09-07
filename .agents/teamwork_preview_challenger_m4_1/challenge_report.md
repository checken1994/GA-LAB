# BÁO CÁO PHẢN BIỆN THỰC NGHIỆM ĐỘC LẬP (EMPIRICAL CHALLENGE REPORT)
## KIỂM TOÁN TÍNH ĐỒNG THỜI VÀ ĐỘ BỀN VỮNG CỦA SCP TASK KERNEL

- **Mã định danh**: `CHALLENGE-TASK-KERNEL-M4-01`
- **Tác tử thực hiện (Challenger)**: `teamwork_preview_challenger_m4_1` (Vai trò: `critic`, `specialist`)
- **Đối tượng phản biện**: Báo cáo Kiểm toán Chênh lệch `DELTA_AUDIT_REPORT.md` và tập kịch bản thăm dò `.agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`
- **Mã băm Commit cơ sở (Baseline Git SHA)**: `075c974db24cdcdf2a39ee99348bf4eddf909703` (Git snapshot: `fc272cf` / `f0ed761`)
- **Bộ quy tắc áp dụng**: SCP DNA (29 nguyên lý cốt lõi, đặc biệt DNA #1, #5, #14, #19, #22, #26), Reality Verifier (Levels A-D), FA-01 đến FA-10
- **Phán quyết tổng thể (Final Verdict)**: **APPROVE (PHÊ DUYỆT CÓ HIỆU CHỈNH KỸ THUẬT)** — Xác nhận các lỗ hổng cướp quyền (Rogue Worker Hijack), bỏ qua khóa thời hạn (Stale Lease Bypass), thiếu khóa lạc quan (Missing OCC) và mất an toàn đồng thời đa tiến trình là **LỖ HỔNG THỰC TẾ, CỐT LÕI VÀ TÁI LẬP ĐƯỢC 100%**. Đồng thời, phản biện và hiệu chỉnh một giả định sai của Explorer về cơ chế timeout của SQLite (Probe 3).

---

## 1. TỔNG QUAN PHẢN BIỆN (CHALLENGE SUMMARY)

**Đánh giá rủi ro kiến trúc tổng thể (Overall Risk Assessment)**: **CRITICAL (NGUY CƠ SỤP ĐỔ HẠT NHÂN)**

Kiểm toán viên tiền trạm (Explorer Survey 1) đã đưa ra 4 phát hiện về Task Kernel:
1. *Flaw 1*: Rogue Worker chiếm đoạt trạng thái tác vụ qua lỗ hổng biến bộ nhớ `_LEASE_CONTEXT`.
2. *Flaw 2*: Bỏ qua kiểm tra thời hạn thuê (Expired Lease Bypass) khi gọi từ ngữ cảnh mới.
3. *Flaw 3*: SQLite bị khóa và sụp đổ tiến trình (`OperationalError: database is locked`) sau 300ms tranh chấp.
4. *Flaw 4*: Ghi đè phiên bản mù quáng (Blind Version Increment) do thiếu kiểm tra điều kiện lạc quan (`WHERE version=?`).

Qua quá trình thực nghiệm đối kháng độc lập (Adversarial Empirical Verification), Challenger xác nhận:
- **Flaw 1, Flaw 2, Flaw 4 là HOÀN TOÀN CHÍNH XÁC, CỰC KỲ NGUY HIỂM VÀ LÀ LỖ HỔNG BẢN CHẤT CỦA KIẾN TRÚC MÃ NGUỒN**, không phải là tạo tác do môi trường kiểm thử (not harness artifacts).
- **Flaw 3 bị HIỂU SAI VỀ MẶT THỜI GIAN TIMEOUT**: Explorer giả định SQLite sẽ crash sau 300ms do vòng lặp 3 lần sleep (0.05s, 0.10s, 0.15s) trong `SQLiteKernelStorage.begin()`. Thực nghiệm đối kháng chứng minh SQLite được bảo vệ bởi `PRAGMA busy_timeout=10000` (10s) và `timeout=10`, do đó các giao dịch giữ khóa 0.5s, 1.0s hay 10.5s **KHÔNG HỀ BỊ CRASH** mà tự động đợi và thành công. Mặc dù nút thắt cổ chai đơn ghi (Single-Writer Serialization) của SQLite vẫn là rủi ro hệ thống, tuyên bố "sập sau 300ms" là một ảo giác đồng thuận cần được hiệu chỉnh.

---

## 2. KẾT QUẢ THỰC NGHIỆM ĐỐI KHÁNG (STRESS TEST & EMPIRICAL RESULTS)

### 2.1. Chạy kịch bản nguyên bản của Explorer (`probe_kernel_flaws.py`)
- **Lệnh thực thi**: `python .agents/teamwork_preview_explorer_survey_1/probe_kernel_flaws.py`
- **Kết quả quan sát thực tế từ terminal**:
  ```text
  STARTING TASK KERNEL CONCURRENCY & DURABILITY PROBE (FA-09)
  ======================================================================
  PROBE 1: Rogue Worker Hijack via In-Memory _LEASE_CONTEXT Bypass
  ======================================================================
  [Worker A] Claimed lease lease_32cf324ee7b42d5b0d83c85f (token=1).
  [Worker A] Current task state: RUNNING
  [Worker B] Connected to same database without lease.
  [Worker B] HIJACKED task-omega-1 to state: HUMAN_REVIEW
  [Worker A CRASHED] Legitimate worker failed with: InvalidTransition: HUMAN_REVIEW->VERIFYING

  ======================================================================
  PROBE 2: Expired Lease Bypass via Fresh Context (Unfenced Transition)
  ======================================================================
  [k1] Task started with 1.0s TTL lease (token=1).
  [k1] 1.2 seconds elapsed. Lease has expired on wall-clock.
  [k1 correctly blocked in memory] StaleLease: lease_5048ea2b8738c64f88c25207
  [k2 BYPASS SUCCESS] Task transitioned to: VERIFYING by unfenced_bypasser!

  ======================================================================
  PROBE 3: Multi-Process SQLite BEGIN IMMEDIATE Lockout Contention
  ======================================================================

  ======================================================================
  PROBE 4: Missing Optimistic Lock (Blind Version Increment Overwrite)
  ======================================================================
  [Initial] Task created with version=1
  [After Worker 1] State: PLANNING, Version: 2
  [After Worker 2] State: CANCELLED, Version: 3
  [Vulnerability] Worker 2 blindly updated state without checking if version was still 1!

  ALL PROBES COMPLETED.
  ```

### 2.2. Phân tích đối kháng chuyên sâu qua bộ thử độc lập (`verify_kernel_stress.py`)
Challenger đã xây dựng và thực thi một bộ thử độc lập có đồng bộ hóa (Multi-thread, Multi-process Event/Barrier):

| Thử nghiệm (Test Case) | Kịch bản đối kháng | Kết quả dự đoán | Kết quả thực tế quan sát được | Đánh giá |
|---|---|---|---|---|
| **Test 1: Multi-Process Lock Contention** | Process 1 giữ `BEGIN IMMEDIATE` 1.0s; Process 2 đồng bộ gọi `_begin()` | Explorer tuyên bố crash sau 300ms | `('SUCCESS', 0.975s)` — Process 2 đợi 0.975s và thành công, không crash! | **CHALLENGED (Giả định 300ms của Explorer là SAI)** |
| **Test 2: Multi-Thread Rogue Hijack** | Worker A giữ lease trên Thread 1; Rogue Worker trên Thread 2 dùng chung instance `TaskKernel` | Rogue thread bị chặn nếu lease gắn theo object | Rogue thread cướp quyền thành công sang `HUMAN_REVIEW`, Worker A crash `InvalidTransition` | **CONFIRMED (Lỗ hổng ContextVar thread-isolated)** |
| **Test 3: Multi-Process Rogue Hijack** | Worker A ở Process 1 giữ lease; Process 2 mở `db_path` và gọi `transition` | Process 2 bị từ chối do không có lease | `('SUCCESS', 'HUMAN_REVIEW')` — Process 2 cướp quyền, Worker A crash khi verify | **CONFIRMED (Lỗ hổng sống trong RAM, mất tác dụng liên tiến trình)** |
| **Test 4: Concurrent OCC Lost Update** | 2 Worker cùng đọc version 1; Worker 1 chuyển `PLANNING`, Worker 2 chuyển `CANCELLED` | Hệ thống OCC phải reject Worker 2 | Cả hai transition đều ghi thành công, version tăng lên 3 mù quáng | **CONFIRMED (Thiếu vị từ WHERE version=?)** |

---

## 3. CÁC ĐIỂM PHẢN BIỆN CHI TIẾT (DETAILED CHALLENGES)

### 3.1. [CRITICAL] Challenge 1: Lỗ hổng Cướp quyền Tác vụ & Vô hiệu hóa Hàng rào Khóa do Cơ chế `_LEASE_CONTEXT`
- **Vấn đề mã nguồn**:
  Tại `scp/task_kernel.py`:
  - Dòng 158–160: `_LEASE_CONTEXT: ContextVar[dict[tuple[int, str], str]] = ContextVar("scp_task_kernel_lease_context", default={})`
  - Dòng 231–233:
    ```python
    lease_id = _bound_lease_id(self, task_id)
    if not lease_id:
        return _original_transition(self, task_id, to_state, actor, reason, payload, event_id)
    ```
- **Phân tích cơ chế gãy đổ (Failure Mechanism)**:
  1. `_bound_lease_id` phụ thuộc vào `(id(kernel), task_id)` lưu trong `ContextVar` của tiến trình Python hiện hành.
  2. Khi bất kỳ worker nào chạy ở tiến trình khác (Multi-process worker pool, CLI, hoặc microservice độc lập), hoặc trong luồng (`threading.Thread`) khác mà không kế thừa context, hoặc đơn giản là tạo mới một đối tượng `worker_b = TaskKernel(db_path)`:
     $$\text{ContextVar}(W_B) = \emptyset \implies \text{lease\_id} = \text{None}$$
  3. Dòng 233 lập tức chuyển tiếp (delegate) sang `_original_transition()` (`scp/task_kernel_parts/taskkernel.py:114`).
  4. Trong `_original_transition()`: Không có **BẤT KỲ DÒNG CODE NÀO** kiểm tra xem tác vụ `task_id` hiện có đang được gắn lease hay không, ai là người sở hữu lease, hoặc lease có bị hết hạn hay không. Nó chỉ kiểm tra `to_state in ALLOWED_TRANSITIONS[old_state]` và thực thi trực tiếp câu lệnh SQL:
     ```sql
     UPDATE tasks SET state=?, version=version+1, updated_at=? WHERE task_id=?
     ```
- **Kịch bản tấn công / Gãy đổ thực tế**:
  - Worker A được cấp quyền lease hợp lệ, chuyển task sang `RUNNING` và đang thực thi công việc nặng (ví dụ: giao dịch tài chính hoặc chạy sandbox tool).
  - Rogue Worker B (hoặc một tiến trình giám sát lỗi) gọi `kernel.transition(task_id, "HUMAN_REVIEW")` hoặc `"CANCELLED"`. Lệnh ghi đè thành công vào SQLite.
  - Khi Worker A hoàn thành và gọi `transition(task_id, "VERIFYING")`: TaskKernel ném lỗi `InvalidTransition: HUMAN_REVIEW->VERIFYING`. Worker A sụp đổ hoàn toàn, tác vụ rơi vào trạng thái bế tắc hoặc chạy trùng lặp khi hồi phục.
- **Phạm vi tác động (Blast Radius)**: Phá vỡ định lý bất biến **INV-01 (Durable State & Lease Fencing)**. Bất kỳ tiến trình nào có quyền mở tệp SQLite đều có thể hủy hoại lifecycle của toàn bộ tác tử trong hệ thống mà không cần chứng chỉ thẩm quyền.
- **Biện pháp khắc phục kiến trúc (Mitigation)**:
  - Loại bỏ hoàn toàn `_LEASE_CONTEXT` trong RAM.
  - Chuyển `fencing_token` và `active_lease_id` thành các cột bắt buộc trong bảng `tasks` ở cơ sở dữ liệu.
  - Phương thức `transition()` bắt buộc phải nhận tham số `fencing_token: int`.
  - Cưỡng chế cập nhật nguyên tử có điều kiện ở cấp độ SQL (Atomic Conditional SQL):
    ```sql
    UPDATE tasks 
    SET state = :to_state, version = version + 1, updated_at = :now 
    WHERE task_id = :task_id 
      AND version = :expected_version 
      AND (active_lease_id IS NULL OR active_lease_id = :lease_id);
    ```

---

### 3.2. [HIGH] Challenge 2: Lỗ hổng Vượt mặt Khóa Hết hạn (Stale Lease Bypass via Fresh Context)
- **Vấn đề mã nguồn**:
  - Tại `scp/task_kernel_parts/taskkernel.py:228`, phương thức `_assert_lease` có kiểm tra `lease['expires_at'] <= now`.
  - Tuy nhiên, phương thức này **CHỈ ĐƯỢC GỌI** khi `lease_id` tồn tại trong `_LEASE_CONTEXT` (dòng 239 trong `scp/task_kernel.py`).
- **Phân tích đối kháng**:
  - Khi Worker A bị quá hạn thuê (wall-clock expiry vượt quá TTL):
    - Nếu Worker A gọi `transition`, biến `_LEASE_CONTEXT` của nó nhận diện được `lease_id`, gọi `_assert_lease` và ném ngoại lệ `StaleLease`. Điều này tạo ra **ảo giác an toàn (False Sense of Security)** trong các bài unit test đơn luồng chạy cùng một đối tượng `TaskKernel`.
    - Nhưng nếu Worker A bị sập và khởi động lại, hoặc một tiến trình phục hồi (Recovery Worker) mở lại tác vụ, `_LEASE_CONTEXT` hoàn toàn trống rỗng!
    - Tiến trình này gọi `transition(task_id, ...)` và vượt qua hoàn toàn bộ lọc `_assert_lease`, thực thi chuyển trạng thái trên một tác vụ đã hết hạn mà không bị chặn lại.
- **Phán quyết**: Khẳng định phát hiện của Explorer là hoàn toàn chuẩn xác. Rào chắn hết hạn hiện tại là **rào chắn giả lập trong bộ nhớ (In-Memory Mock Guard)**, không có giá trị bảo vệ thực tế trên môi trường sản xuất đa tiến trình.

---

### 3.3. [MEDIUM - CHALLENGED] Challenge 3: Giả định Sai lệch về Ngưỡng Timeout 300ms trong Tranh chấp Đa tiến trình SQLite
- **Giả định bị phản biện của Explorer**:
  Báo cáo `DELTA_AUDIT_REPORT.md` (dòng 10, 680) và `probe_kernel_flaws.py` tuyên bố:
  > *"3. Multi-Process Contention Crash (OperationalError: database is locked after 300ms timeout)."*
  Explorer lập luận rằng vòng lặp 3 lần retry với sleep $(0.05 + 0.10 + 0.15) = 0.30s$ trong `SQLiteKernelStorage.begin()` sẽ làm hệ thống crash ngay sau 300ms nếu có tranh chấp khóa ghi.
- **Thực nghiệm chứng minh giả định sai**:
  Challenger đã phân tích mã nguồn tầng lưu trữ `scp/kernel_storage.py:101-110`:
  ```python
  def _make_connection(self) -> sqlite3.Connection:
      conn = sqlite3.connect(
          self.db_path, timeout=10, isolation_level=None, check_same_thread=False
      )
      ...
      conn.execute("PRAGMA busy_timeout=10000")
      return conn
  ```
  Khi `self._get_conn().execute("BEGIN IMMEDIATE")` chạy:
  1. Trình điều khiển C của SQLite **không trả về lỗi ngay lập tức**. Hàm `sqlite3_step()` kích hoạt cơ chế `busy_handler` nội tại và chủ động chờ đợi trong kernel/OS cho đến khi hết `busy_timeout` (10,000ms = 10 giây) mới ném ngoại lệ `OperationalError: database is locked`.
  2. Mỗi lần retry trong vòng lặp 3 lần của `begin()` đều được hậu thuẫn bởi 10 giây chờ đợi của SQLite. Do đó, tổng thời gian chịu tải trước khi ném ngoại lệ thực tế là **hơn 30 giây**, không phải 300ms!
  3. Khi chạy `probe_kernel_flaws.py` trên Windows: Tiến trình Process 2 không hề bị crash như Explorer tuyên bố.
  4. Khi Challenger chạy thử nghiệm thực tế với tiến trình giữ khóa trong 1.0 giây và 10.5 giây: Tiến trình đối thủ vẫn đợi thành công (`k2 succeeded in 10.53s`) và không xuất hiện lỗi khóa cơ sở dữ liệu.
- **Đánh giá rủi ro thực tế (Calibrated Assessment)**:
  Mặc dù giả thuyết "crash sau 300ms" là sai về mặt số liệu thực nghiệm, rủi ro kiến trúc về mặt dài hạn vẫn hiện hữu: SQLite sử dụng cơ chế khóa toàn bộ tệp cơ sở dữ liệu cho tác vụ ghi (Database-Level Exclusive Write Lock). Trong mô hình Agent OS phân tán với hàng trăm agent và công cụ ngoại vi chạy đồng thời, việc dồn toàn bộ tác vụ chuyển trạng thái vào một tệp SQLite duy nhất sẽ gây ra hiện tượng nghẽn cổ chai nghiêm trọng (Lock Starvation) và độ trễ p99 tăng vọt.

---

### 3.4. [HIGH] Challenge 4: Thiếu Cơ chế Khóa Lạc quan (Blind Version Increment Overwrite)
- **Vấn đề mã nguồn**:
  Tại `scp/task_kernel_parts/taskkernel.py:142` và `scp/task_kernel.py:275`:
  ```sql
  UPDATE tasks SET state=?, version=version+1, updated_at=? WHERE task_id=?
  ```
- **Phân tích đối kháng**:
  - Giao diện `transition()` không nhận `expected_version`.
  - Giả sử Worker 1 và Worker 2 cùng đọc bản ghi tác vụ tại `version = 1`.
  - Worker 1 lập luận logic nghiệp vụ dựa trên `version 1` và chuyển trạng thái sang `PLANNING` (`version` thành 2).
  - Worker 2 lập luận logic nghiệp vụ độc lập (cũng dựa trên dữ liệu cũ của `version 1`) và chuyển trạng thái sang `CANCELLED`.
  - Thay vì bị từ chối do trạng thái cơ sở đã bị thay đổi (Optimistic Concurrency Control failure), câu lệnh SQL của Worker 2 vẫn thực thi trót lọt, nâng `version` lên 3.
  - Toàn bộ kết quả tính toán của Worker 1 bị ghi đè hoàn toàn trong im lặng mà không có bất kỳ cảnh báo xung đột (Conflict Warning) nào được phát ra.
- **Phán quyết**: Khẳng định phát hiện của Explorer là hoàn toàn chuẩn xác. Đây là vi phạm trực tiếp đối với mô hình xử lý giao dịch phân tán chuẩn tắc.

---

## 4. BẢNG TỔNG HỢP ĐỐI CHIẾU CÁC NĂNG LỰC TASK KERNEL (CONTRACT MATRIX)

Dựa trên chuẩn kiểm toán `scp-task-kernel-review`:

| Năng lực bắt buộc (Capability) | Hiện trạng trong Code | Đã chứng minh Runtime? | Kết luận Kiểm toán & Phản biện |
|---|---|:---:|---|
| **Task Identity** | Có ID, owner, state, risk | B (Một phần) | Đạt chuẩn nhận dạng cơ bản. |
| **State Machine** | Gồm 15 trạng thái chuẩn | B (Một phần) | Bị thủng: Rogue worker có thể chuyển trạng thái bất kỳ lúc nào nếu không gắn context. |
| **Lease Fencing** | `ContextVar` trong bộ nhớ RAM | **KHÔNG (Thất bại)** | **CRITICAL FLAW**: Không có giá trị trên môi trường đa tiến trình / đa luồng. |
| **Event Journal** | Bảng `events` append-only | B (Một phần) | Ghi nhận sự kiện đầy đủ, nhưng thiếu kiểm tra chữ ký/token của worker. |
| **Projection Rebuild** | Có phương thức `projection` | B (Một phần) | Hoạt động được ở mức đơn giản, nhưng bị ảnh hưởng bởi các event ghi đè bất hợp pháp. |
| **Optimistic Lock** | Chỉ tăng `version=version+1` | **KHÔNG (Thất bại)** | **HIGH FLAW**: Thiếu vị từ `WHERE version = :expected_version`. |
| **Multi-Process Concurrency**| Dùng SQLite WAL + Retry | B (Một phần) | Không crash sau 300ms như Explorer nghĩ, nhưng bị giới hạn bởi single-writer lock. |
| **Kill Switch** | Bảng `control` có epoch | B (Một phần) | Có kiểm tra epoch, nhưng bị bypass nếu gọi qua `_original_transition`. |

**Đánh giá Cấp độ Trưởng thành Hạt nhân**: **`ORCHESTRATOR_ONLY / KERNEL_PARTIAL`** (Tuyệt đối chưa đủ điều kiện gọi là Agent OS).

---

## 5. PHÁN QUYẾT CUỐI CÙNG & KIẾN NGHỊ (FINAL VERDICT & ACTIONABLE RECOMMENDATIONS)

### 5.1. Phán quyết chính thức: **`APPROVE (PHÊ DUYỆT BÁO CÁO CÓ HIỆU CHỈNH)`**
Challenger xác nhận toàn bộ các phát hiện nòng cốt của `DELTA_AUDIT_REPORT.md` về sự yếu kém của Task Kernel là **CHÍNH XÁC VÀ BẮT BUỘC PHẢI KHẮC PHỤC** trước khi bước vào giai đoạn phát hành (Release Gate M5).

### 5.2. Kiến nghị nâng cấp kiến trúc bắt buộc (Mandatory Upgrades for Omega)
1. **Xóa bỏ vĩnh viễn biến `_LEASE_CONTEXT`**: Tuyệt đối không lưu trữ quyền hạn ủy thác trong RAM/ContextVar.
2. **Thiết lập Fencing Token ở cấp độ Cơ sở dữ liệu**:
   - Thêm cột `active_lease_id TEXT` và `fencing_token INTEGER` vào bảng `tasks`.
   - Mọi phương thức thay đổi trạng thái tác vụ (`transition`, `checkpoint`, `complete`, `fail`) bắt buộc phải nhận `lease_id: str` và `expected_version: int`.
3. **Cưỡng chế Khóa Lạc quan Nguyên tử (Atomic OCC)**:
   ```sql
   UPDATE tasks 
   SET state = :to_state, 
       version = version + 1, 
       updated_at = :now 
   WHERE task_id = :task_id 
     AND version = :expected_version 
     AND active_lease_id = :lease_id;
   ```
   Nếu số dòng cập nhật trả về bằng 0 (`rowcount == 0`), Task Kernel lập tức rollback và ném ngoại lệ `StaleLease` hoặc `ConcurrencyConflictError`.
4. **Hiệu chỉnh tài liệu kiểm toán**: Cập nhật lại phân tích về Probe 3 trong các báo cáo tổng hợp để loại bỏ khẳng định "SQLite crash sau 300ms", thay thế bằng phân tích chính xác về giới hạn đơn luồng ghi và trần timeout 30 giây.
