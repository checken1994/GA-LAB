# Handoff Report — Explorer P2-1 (Call Graph Navigation & SQL UPDATE Audit)

- **To**: Orchestrator 3 (`4aab71c9-e6ee-472b-8c41-c64e48735a24`)
- **From**: Explorer P2-1 (`teamwork_preview_explorer`)
- **Working Directory**: `c:\Users\check\Downloads\scp\.agents\explorer_p2_1`
- **Milestone**: M1 (Deep Survey & Call Graph Audit)
- **Status**: Completed (Hard Handoff)

---

## 1. Observation

1. **Khảo sát cấu trúc bảng và schema trong `scp/task_kernel_parts/taskkernel.py:54`**:
   - Bảng `tasks` có cột `version INTEGER NOT NULL DEFAULT 1`.
   - Bảng `leases` (Line 54) gồm các cột: `lease_id`, `task_id`, `attempt_id`, `worker_id`, `issued_at`, `expires_at`, `heartbeat_at`, `fencing_token`, `global_kill_epoch`, `released`. **Không có cột `version`**.
   - Bảng `idempotency` (Line 54) gồm các cột: `logical_key`, `task_id`, `step_id`, `action_type`, `resource_identity`, `status`, `result_ref`, `created_at`. **Không có cột `version`**.
   - Bảng `control` (Line 54) gồm các cột: `id`, `global_kill`, `global_kill_epoch`. **Không có cột `version`**.
   - Bảng `checkpoints` và `events`: Hoàn toàn không có câu lệnh `UPDATE` nào trong mã nguồn (Append-Only).

2. **Toàn bộ 11 câu lệnh `UPDATE leases` đều thiếu OCC và không check version**:
   - `taskkernel.py:388`: `UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?`
   - `taskkernel.py:214, 416, 441, 723`: `UPDATE leases SET released=1 WHERE lease_id=?`
   - `taskkernel.py:576, 626, 756, 842, 923` & `task_kernel.py:304`: `UPDATE leases SET released=1 WHERE task_id=?`

3. **Toàn bộ 8 câu lệnh `UPDATE idempotency` đều thiếu OCC và không check version**:
   - `task_kernel.py:188`: `UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?`
   - `task_kernel.py:232`: `UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?`
   - `task_kernel.py:293`: `UPDATE idempotency SET status=?,result_ref=? WHERE logical_key=?`
   - `taskkernel.py:610, 614, 618`: `UPDATE idempotency SET status=... WHERE logical_key=?`
   - `taskkernel.py:660`: `UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?`
   - `taskkernel.py:687`: `UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?`

4. **Tồn tại 1 điểm Blind Overwrite trên bảng `tasks`**:
   - `taskkernel.py:293` (trong `claim_next` khi deadline quá hạn):
     `self.conn.execute("UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))`
     Mệnh đề WHERE chỉ có `WHERE task_id=?`, hoàn toàn thiếu `AND version=?`.

5. **Call Graph Navigation Map từ các module gọi vào Kernel**:
   - `scp/ask_kernel_adapter.py:161` calls `claim` (`taskkernel.py:251`)
   - `scp/ask_kernel_adapter.py:162` calls `start` (`taskkernel.py:340`)
   - `scp/ask_kernel_adapter.py:163` calls `idempotency_claim` (`task_kernel.py:150`)
   - `scp/ask_kernel_adapter.py:384, 395, 430` calls `transition` (`taskkernel.py:122`)
   - `scp/ask_kernel_adapter.py:393` calls `commit_verification_result` (`taskkernel.py:693`) -> `commit_completed` (`taskkernel.py:700`)
   - `scp/hands/task_kernel_bridge.py:309` calls `heartbeat` (`taskkernel.py:370`)
   - `scp/hands/task_kernel_bridge.py:411` calls `claim` (`taskkernel.py:251`)
   - `scp/hands/task_kernel_bridge.py:417` calls `start` (`taskkernel.py:340`)
   - `scp/hands/task_kernel_bridge.py:419` calls `idempotency_claim` (`task_kernel.py:150`)
   - `scp/hands/task_kernel_bridge.py:441` calls `checkpoint` (`taskkernel.py:457`)
   - `scp/hands/task_kernel_bridge.py:506, 664` calls `release` (`taskkernel.py:427`)
   - `scp/hands/task_kernel_bridge.py:520` calls `idempotency_complete` (`task_kernel.py:206`)
   - `scp/hands/task_kernel_bridge.py:522` calls `commit_verification_result` (`taskkernel.py:693`)
   - `scp/hands/task_kernel_bridge.py:688, 690` calls `enter_reconciling` và `reconcile_unknown`
   - `scp/api/background_jobs.py:207` calls `expire_leases` (`taskkernel.py:395`)
   - `scp/api/background_jobs.py:226` calls `auto_reconcile_orphans` (`taskkernel.py:772`)
   - `scp/api_server_parts/lifespan.py:267` calls `recover_on_boot` (`taskkernel.py:890`)

---

## 2. Logic Chain

1. **Từ Observation 1 & 2**: Bảng `leases` không có trường `version`. Câu lệnh tại `taskkernel.py:388` (`UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?`) chỉ lọc theo `lease_id`. Nếu lease đã bị thu hồi (`released=1`) bởi watchdog (`expire_leases`) hay operator (`set_task_kill`), một worker chạy trễ vẫn có thể thực thi heartbeat thành công, ghi đè `expires_at` vào tương lai. Đây là lỗi **Heartbeat Zombie Resurrection**, phá vỡ tính phân định worker còn sống/hết hạn.
2. **Từ Observation 1 & 3**: Bảng `idempotency` không có trường `version`. Hàm `idempotency_claim` (`task_kernel.py:188` và `taskkernel.py:660`) thực hiện pattern `SELECT` rồi sau đó `UPDATE ... WHERE logical_key=?`. Khi có 2 worker đồng thời claim lại một task có trạng thái `RETRYABLE`, cả 2 đều đọc thấy `RETRYABLE`, cả 2 đều thực hiện `UPDATE`, và cả 2 đều nhận `(logical_key, True)`. Điều này vi phạm tính bất biến Idempotency và Atomic Fencing.
3. **Từ Observation 4**: Trong `claim_next` (`taskkernel.py:293`), khi task hết hạn `deadline_ms`, câu lệnh cập nhật `tasks` sang `FAILED` chỉ dùng `WHERE task_id=?` mà không so khớp `version`. Nếu tại đúng thời điểm đó, một worker khác đang claim hoặc transition task này (làm tăng version), lệnh ở dòng 293 sẽ ghi đè mù lên task.
4. **Từ Observation 5**: Call Graph Navigation Map cho thấy tất cả các luồng xử lý chính ngạch (`/ask` route qua `AskKernelAdapter`, Hands side effects qua `TaskKernelHandsBridge`, và các background worker) đều hội tụ về tập các phương thức này trong `taskkernel.py`. Do đó, bất kỳ sự cố race condition nào ở các bảng vệ tinh `leases` và `idempotency` đều sẽ trực tiếp gây sụp đổ tính nhất quán của Agent OS.

---

## 3. Caveats

1. **Phạm vi kiểm toán**: Cuộc kiểm toán tập trung vào mã nguồn nội tại của SCP Task Kernel và các adapter liên quan trực tiếp. Các bảng ngoài hệ sinh thái TaskKernel (như `worker_jobs` trong `deterministic_worker.py` hay `knowledge` trong `fastlearningengine.py`) có sử dụng UPDATE riêng, nhưng nằm ngoài ranh giới TaskKernel INV-01.
2. **Nguyên tắc Read-Only**: Explorer tuân thủ nghiêm ngặt nguyên tắc chỉ điều tra (read-only), không thực hiện bất kỳ chỉnh sửa mã nguồn sản phẩm hay test nào.
3. **Yêu cầu FA-09**: Chưa viết script exploit trực tiếp để mutate hệ thống, nhưng đã thiết kế kịch bản chi tiết cho Milestone M2 trong `analysis.md`.

---

## 4. Conclusion

1. **Kết luận kiểm toán**: Tử huyệt GAP-02 tồn tại trên thực tế tại 4 điểm trọng yếu:
   - `leases` thiếu version và bị lỗi Heartbeat Zombie Resurrection (`taskkernel.py:388`).
   - `idempotency` thiếu version và bị lỗi Double-Claim Race (`task_kernel.py:188` & `taskkernel.py:660`).
   - `idempotency` bị Blind Completion Overwrite (`task_kernel.py:232` & `taskkernel.py:687`).
   - `tasks` bị Blind Overwrite tại `taskkernel.py:293` trong `claim_next`.
2. **Kế hoạch hành động cụ thể cho M2 & M3**:
   - **Milestone M2**: Viết script probe chứng minh thực tế trên terminal:
     1. Double-claim trên `idempotency` (2 worker cùng claim key `RETRYABLE`).
     2. Heartbeat resurrection trên `leases` (heartbeat thành công trên lease đã `released=1`).
   - **Milestone M3**:
     1. Thêm `version INTEGER NOT NULL DEFAULT 1` vào `leases` và `idempotency`.
     2. Sửa toàn bộ lệnh UPDATE sang pattern:
        `UPDATE <table> SET ..., version=version+1 WHERE id=? AND version=? [AND condition]`
        Kiểm tra `rowcount == 1`, nếu không raise `OptimisticLockError`.

---

## 5. Verification Method

1. **Kiểm tra sự tồn tại của các câu lệnh UPDATE**:
   - Chạy lệnh:
     ```powershell
     python -c "import ast, re; lines = open('scp/task_kernel_parts/taskkernel.py', encoding='utf-8').readlines(); print(lines[292].strip()); print(lines[387].strip())"
     ```
     Sẽ thấy rõ dòng 293 thiếu `AND version=?` và dòng 388 chỉ có `WHERE lease_id=?`.
2. **Kiểm tra schema thiếu cột version**:
   - Chạy lệnh:
     ```powershell
     python -c "from scp.task_kernel import TaskKernel; k = TaskKernel(':memory:'); print([r['name'] for r in k.conn.execute('PRAGMA table_info(leases)').fetchall()]); print([r['name'] for r in k.conn.execute('PRAGMA table_info(idempotency)').fetchall()])"
     ```
     Sẽ thấy danh sách cột của `leases` và `idempotency` **hoàn toàn không có cột `version`**.
3. **Kiểm tra full regression hiện tại**:
   - `pytest tests/T04_kernel -q`
