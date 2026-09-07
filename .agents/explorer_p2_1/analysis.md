# Báo Cáo Kiểm Toán Toàn Diện: SQL UPDATE & Call Graph Navigation (GAP-02)

- **Người thực hiện**: Explorer P2-1 (`teamwork_preview_explorer`)
- **Working directory**: `c:\Users\check\Downloads\scp\.agents\explorer_p2_1`
- **Thời điểm hoàn thành**: 2026-09-07T00:01:00Z
- **Phạm vi kiểm toán**: `scp/kernel_storage.py`, `scp/task_kernel.py`, `scp/task_kernel_parts/taskkernel.py`, các DAO/subsystem vệ tinh liên quan (`ask_kernel_adapter.py`, `hands/task_kernel_bridge.py`, `api/background_jobs.py`, `api_server_parts/lifespan.py`, v.v.).

---

## 1. Tóm Tắt Điều Hành (Executive Summary)

Pha 1 của Kế hoạch Tiến hóa đã xử lý OCC cho bảng `tasks` trong hầu hết các state transition. Tuy nhiên, qua cuộc kiểm toán AST và Source Code toàn diện cho **Tử huyệt GAP-02 (OCC Blind Overwrites)**:
1. **Bảng vệ tinh `leases`**: Hoàn toàn **KHÔNG có cột `version`** trong schema (`taskkernel.py:54`). Toàn bộ **11 lệnh UPDATE** trên `leases` đều không có kiểm tra version (`WHERE lease_id=?` hoặc `WHERE task_id=?`). Rủi ro nghiêm trọng nhất: **Lỗ hổng Heartbeat Resurrection (Hồi sinh Lease cũ)** — Một worker bị timeout/expire/release khi gọi `heartbeat()` sẽ chạy lệnh `UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?` mù, ghi đè và làm sống lại lease đã bị thu hồi mà không hề kiểm tra trạng thái hay version!
2. **Bảng vệ tinh `idempotency`**: Hoàn toàn **KHÔNG có cột `version`** trong schema (`taskkernel.py:54`). Toàn bộ **8 lệnh UPDATE** trên `idempotency` đều không kiểm tra version (`WHERE logical_key=?`). Rủi ro nghiêm trọng: **Lỗ hổng Double-Claim Race** — Hai luồng/worker cùng thấy `status == 'RETRYABLE'` sẽ cùng thực thi `UPDATE ... SET status='CLAIMED'` và cả 2 đều tin rằng mình đã claim thành công, phá vỡ tính đơn nhiệm (single-flight execution) và tính lũy kế (idempotency guarantee).
3. **Bảng `tasks` vẫn còn 2 điểm Ghi Đè Mù**:
   - **`claim_next` (Line 293)**: Khi task hết hạn deadline, kernel thực thi:
     `UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=?`
     Mệnh đề WHERE chỉ có `WHERE task_id=?` mà **hoàn toàn thiếu `AND version=?`**! Nếu task đang được xử lý hoặc cập nhật đồng thời bởi worker khác, lệnh này ghi đè mù!
   - **`rebuild_projection` (Line 1005)**: `UPDATE tasks SET state=?,version=version+1,... WHERE task_id=?` không kiểm tra version (do bản chất là projection replay từ journal).
4. **Bảng `control` & `queue_accounts`**: Không có cột `version`. Bảng `control` có 1 lệnh `UPDATE control SET global_kill=?,global_kill_epoch=? WHERE id=1` mù.
5. **Bảng `checkpoints` và `events`**: Hoàn toàn Append-Only (chỉ có INSERT, 0 câu lệnh UPDATE).

---

## 2. Danh Mục Toàn Bộ Câu Lệnh SQL UPDATE Trong Kernel & Bảng Vệ Tinh

### 2.1. Bảng `tasks` (16 câu lệnh UPDATE)

| # | File & Line | Hàm / Phương thức | Columns Được Cập Nhật | Mệnh Đề WHERE | Có Check Version? | Rủi Ro Concurrency / Blind Overwrite |
|---|---|---|---|---|---|---|
| T01 | `scp/task_kernel.py:297` | `_reconcile_unknown_complete_outcomes` | `state='HUMAN_REVIEW'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T02 | `scp/task_kernel_parts/taskkernel.py:223` | `transition` | `state=?`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T03 | `scp/task_kernel_parts/taskkernel.py:268` | `claim` | `state='LEASED'`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?,` `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T04 | `scp/task_kernel_parts/taskkernel.py:293` | `claim_next` | `state='FAILED'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=?` | **KHÔNG** | **NGUY HIỂM: BLIND OVERWRITE**. Khi deadline hết hạn, ghi đè mù lên task mà không so sánh version |
| T05 | `scp/task_kernel_parts/taskkernel.py:303` | `claim_next` | `state='LEASED'`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> `continue`) |
| T06 | `scp/task_kernel_parts/taskkernel.py:357` | `start` | `state='RUNNING'`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?`, `updated_at=?` | `WHERE task_id=? AND version=? AND (active_lease_id=? OR active_lease_id IS NULL)` | **CÓ** | An toàn (Kiểm tra cả version và lease) |
| T07 | `scp/task_kernel_parts/taskkernel.py:406` | `expire_leases` | `state='RECOVERING'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn |
| T08 | `scp/task_kernel_parts/taskkernel.py:409` | `expire_leases` | `state='HUMAN_REVIEW'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn |
| T09 | `scp/task_kernel_parts/taskkernel.py:412` | `expire_leases` | `state='QUEUED'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn |
| T10 | `scp/task_kernel_parts/taskkernel.py:415` | `expire_leases` | `active_lease_id=NULL`, `active_fencing_token=0`, `version=version+1`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn |
| T11 | `scp/task_kernel_parts/taskkernel.py:443` | `release` | `active_lease_id=NULL`, `active_fencing_token=0`, `version=version+1`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T12 | `scp/task_kernel_parts/taskkernel.py:530` | `record_action_dispatched` | `state='UNKNOWN'`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?,` `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T13 | `scp/task_kernel_parts/taskkernel.py:571` | `enter_reconciling` | `state='RECONCILING'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T14 | `scp/task_kernel_parts/taskkernel.py:621` | `reconcile_unknown` | `state=?`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T15 | `scp/task_kernel_parts/taskkernel.py:719` | `commit_completed` | `state='COMPLETED'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T16 | `scp/task_kernel_parts/taskkernel.py:753` | `set_task_kill` | `state='CANCELLED'`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> raise `StaleLease`) |
| T17 | `scp/task_kernel_parts/taskkernel.py:829` | `auto_reconcile_orphans` | `state=?`, `version=version+1`, `active_lease_id=NULL`, `active_fencing_token=0`, `updated_at=?` | `WHERE task_id=? AND version=?` | **CÓ** | An toàn (Check `cur.rowcount != 1` -> break) |
| T18 | `scp/task_kernel_parts/taskkernel.py:1005` | `rebuild_projection` | `state=?`, `version=version+1`, `active_lease_id=?`, `active_fencing_token=?`, `updated_at=?` | `WHERE task_id=?` | **KHÔNG** | Replay projection từ journal events (được thiết kế idempotent, nhưng không atomic với concurrent writes) |

---

### 2.2. Bảng `leases` (11 câu lệnh UPDATE)

**Schema hiện tại (`taskkernel.py:54`)**:
```sql
CREATE TABLE IF NOT EXISTS leases (
    lease_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    fencing_token INTEGER NOT NULL,
    global_kill_epoch INTEGER NOT NULL,
    released INTEGER NOT NULL DEFAULT 0
);
```
*(Hoàn toàn không có trường `version`)*.

| # | File & Line | Hàm / Phương thức | Columns Được Cập Nhật | Mệnh Đề WHERE | Có Check Version? | Rủi Ro Concurrency / Blind Overwrite |
|---|---|---|---|---|---|---|
| L01 | `scp/task_kernel.py:304` | `_reconcile_unknown_complete_outcomes` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id thành released=1 |
| L02 | `scp/task_kernel_parts/taskkernel.py:214` | `transition` | `released=1` | `WHERE lease_id=?` | **KHÔNG** | Ghi đè mù `released=1` |
| L03 | `scp/task_kernel_parts/taskkernel.py:388` | `heartbeat` | `heartbeat_at=?`, `expires_at=?` | `WHERE lease_id=?` | **KHÔNG** | **TỬ HUYỆT (Heartbeat Resurrection)**: Cập nhật gia hạn lease mà không kiểm tra lease đã bị revoke/release hay chưa |
| L04 | `scp/task_kernel_parts/taskkernel.py:416` | `expire_leases` | `released=1` | `WHERE lease_id=?` | **KHÔNG** | Ghi đè mù `released=1` |
| L05 | `scp/task_kernel_parts/taskkernel.py:441` | `release` | `released=1` | `WHERE lease_id=?` | **KHÔNG** | Ghi đè mù `released=1` |
| L06 | `scp/task_kernel_parts/taskkernel.py:576` | `enter_reconciling` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id |
| L07 | `scp/task_kernel_parts/taskkernel.py:626` | `reconcile_unknown` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id |
| L08 | `scp/task_kernel_parts/taskkernel.py:723` | `commit_completed` | `released=1` | `WHERE lease_id=?` | **KHÔNG** | Ghi đè mù `released=1` |
| L09 | `scp/task_kernel_parts/taskkernel.py:756` | `set_task_kill` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id |
| L10 | `scp/task_kernel_parts/taskkernel.py:842` | `auto_reconcile_orphans` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id |
| L11 | `scp/task_kernel_parts/taskkernel.py:923` | `recover_on_boot` | `released=1` | `WHERE task_id=?` | **KHÔNG** | Ghi đè mù toàn bộ lease của task_id khi boot |

---

### 2.3. Bảng `idempotency` (8 câu lệnh UPDATE)

**Schema hiện tại (`taskkernel.py:54`)**:
```sql
CREATE TABLE IF NOT EXISTS idempotency (
    logical_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    resource_identity TEXT NOT NULL,
    status TEXT NOT NULL,
    result_ref TEXT,
    created_at TEXT NOT NULL
);
```
*(Hoàn toàn không có trường `version`)*.

| # | File & Line | Hàm / Phương thức | Columns Được Cập Nhật | Mệnh Đề WHERE | Có Check Version? | Rủi Ro Concurrency / Blind Overwrite |
|---|---|---|---|---|---|---|
| I01 | `scp/task_kernel.py:188` | `_idempotency_claim_fenced` | `status='CLAIMED'`, `result_ref=NULL` | `WHERE logical_key=?` | **KHÔNG** | **RACE CONDITION**: 2 luồng cùng đọc `RETRYABLE` sẽ cùng UPDATE thành `CLAIMED` và cả 2 đều return `(key, True)` |
| I02 | `scp/task_kernel.py:232` | `_idempotency_complete_fenced` | `status='COMPLETED'`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù kết quả completion mà không kiểm tra status/version nguyên tử tại thời điểm UPDATE |
| I03 | `scp/task_kernel.py:293` | `_reconcile_unknown_complete_outcomes` | `status=?`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù trạng thái `RECONCILED_*` |
| I04 | `scp/task_kernel_parts/taskkernel.py:610` | `reconcile_unknown` | `status='RETRYABLE'`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù thành `RETRYABLE` |
| I05 | `scp/task_kernel_parts/taskkernel.py:614` | `reconcile_unknown` | `status='RECONCILED_APPLIED'`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù thành `RECONCILED_APPLIED` |
| I06 | `scp/task_kernel_parts/taskkernel.py:618` | `reconcile_unknown` | `status='RECONCILED_UNKNOWN'`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù thành `RECONCILED_UNKNOWN` |
| I07 | `scp/task_kernel_parts/taskkernel.py:660` | `idempotency_claim` | `status='CLAIMED'`, `result_ref=NULL` | `WHERE logical_key=?` | **KHÔNG** | Race condition tương tự I01 |
| I08 | `scp/task_kernel_parts/taskkernel.py:687` | `idempotency_complete` | `status='COMPLETED'`, `result_ref=?` | `WHERE logical_key=?` | **KHÔNG** | Ghi đè mù tương tự I02 |

---

### 2.4. Bảng `queue_accounts` & `control`

| # | File & Line | Bảng | Hàm | Columns | Mệnh Đề WHERE | Có Check Version? | Nhận Xét |
|---|---|---|---|---|---|---|---|
| Q01-Q10 | `taskkernel.py:216, 418, 448, 578, 628, 724, 758, 845, 925` & `task_kernel.py:306` | `queue_accounts` | Nhiều hàm | `active=CASE WHEN active>0 THEN active-1 ELSE 0 END` | `WHERE owner=?` | **KHÔNG** | Sử dụng biểu thức nguyên tử trong SQL (`active-1`), nhưng không quản lý version |
| C01 | `taskkernel.py:738` | `control` | `set_global_kill` | `global_kill=?`, `global_kill_epoch=?` | `WHERE id=1` | **KHÔNG** | Ghi đè epoch mù, có thể đua trạng thái toggle giữa 2 operator |

---

## 3. Bản Đồ Định Vị Call Graph Từng Dòng (Line-by-Line Call Graph Navigation Map)

Bản đồ này xác lập chính xác dòng code nào gọi dòng code nào (`FileA:LineX calls FileB:LineY`), kết nối từ tầng API / Adapters / Background Jobs xuống các phương thức chứa câu lệnh UPDATE trong Kernel.

```
[HTTP Request / Cron / LifeSpan]
       │
       ▼
[Adapters & Bridges]
  ├─ scp/ask_kernel_adapter.py
  ├─ scp/hands/task_kernel_bridge.py
  ├─ scp/api/background_jobs.py
  └─ scp/api_server_parts/lifespan.py
       │
       ▼
[TaskKernel Interface & Implementation]
  ├─ scp/task_kernel.py
  └─ scp/task_kernel_parts/taskkernel.py
       │
       ▼
[Kernel Storage Execution Facade]
  └─ scp/kernel_storage.py (execute, begin, commit, rollback)
       │
       ▼
[SQLite Tables: tasks, leases, idempotency, queue_accounts, control]
```

### 3.1. Nhóm Khởi Tạo & Vòng Đời Task (`claim`, `start`, `transition`)

1. **`claim`** (`scp/task_kernel_parts/taskkernel.py:251`):
   - Chứa UPDATE:
     - `taskkernel.py:268`: `UPDATE tasks SET state='LEASED',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:272`: `INSERT INTO queue_accounts ... ON CONFLICT DO UPDATE SET active=active+1,...`
   - **Callers**:
     - `scp/ask_kernel_adapter.py:161` calls `claim` at `scp/task_kernel_parts/taskkernel.py:251` (trong hàm `start_task`)
     - `scp/hands/task_kernel_bridge.py:411` calls `claim` at `scp/task_kernel_parts/taskkernel.py:251` (trong hàm `execute`)
     - `scp/autofix/deterministic_worker.py:478` calls `claim` (trong worker dispatch)

2. **`claim_next`** (`scp/task_kernel_parts/taskkernel.py:281`):
   - Chứa UPDATE:
     - `taskkernel.py:293`: **`UPDATE tasks SET state='FAILED' ... WHERE task_id=?`** *(BLIND OVERWRITE)*
     - `taskkernel.py:303`: `UPDATE tasks SET state='LEASED' ... WHERE task_id=? AND version=?`
     - `taskkernel.py:307`: `INSERT INTO queue_accounts ... ON CONFLICT DO UPDATE`
   - **Callers**:
     - Được gọi bởi các worker rà soát hàng đợi (`worker loop`, `tests/T04_kernel/test_adversarial_kernel_flaws.py:48, 78, 266`).

3. **`start`** (`scp/task_kernel_parts/taskkernel.py:340`):
   - Chứa UPDATE:
     - `taskkernel.py:357`: `UPDATE tasks SET state='RUNNING',version=version+1,... WHERE task_id=? AND version=? AND (active_lease_id=? OR active_lease_id IS NULL)`
   - **Callers**:
     - `scp/ask_kernel_adapter.py:162` calls `start` at `scp/task_kernel_parts/taskkernel.py:340`
     - `scp/hands/task_kernel_bridge.py:417` calls `start` at `scp/task_kernel_parts/taskkernel.py:340`

4. **`transition`** (`scp/task_kernel_parts/taskkernel.py:122`):
   - Chứa UPDATE:
     - `taskkernel.py:214`: `UPDATE leases SET released=1 WHERE lease_id=?`
     - `taskkernel.py:216`: `UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ... WHERE owner=?`
     - `taskkernel.py:223`: `UPDATE tasks SET state=?,version=version+1,... WHERE task_id=? AND version=?`
   - **Callers**:
     - `scp/ask_kernel_adapter.py:160` calls `transition` (chuyển qua `PLANNING`, `READY`, `QUEUED`)
     - `scp/ask_kernel_adapter.py:384` calls `transition` (chuyển sang `VERIFYING`)
     - `scp/ask_kernel_adapter.py:395` calls `transition` (chuyển sang `HUMAN_REVIEW` nếu verify thất bại)
     - `scp/ask_kernel_adapter.py:430` calls `transition` (chuyển sang `FAILED` khi gặp lỗi)
     - `scp/hands/task_kernel_bridge.py:409` calls `transition` (`PLANNING`, `READY`, `QUEUED`)
     - `scp/hands/task_kernel_bridge.py:492` calls `transition` (`FAILED` do policy block)
     - `scp/hands/task_kernel_bridge.py:516` calls `transition` (`VERIFYING`)
     - `scp/hands/task_kernel_bridge.py:626` calls `transition` (`FAILED` do pre-dispatch failure)
     - `scp/task_kernel_parts/taskkernel.py:927` calls `transition` (`HUMAN_REVIEW` trong `recover_on_boot`)
     - `scp/task_kernel_parts/taskkernel.py:930` calls `transition` (`RECOVERING` trong `recover_on_boot`)
     - `scp/task_kernel_parts/taskkernel.py:933` calls `transition` (`QUEUED` trong `recover_on_boot`)

---

### 3.2. Nhóm Lease & Heartbeat (`heartbeat`, `expire_leases`, `release`)

1. **`heartbeat`** (`scp/task_kernel_parts/taskkernel.py:370`):
   - Chứa UPDATE:
     - `taskkernel.py:388`: **`UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?`** *(BLIND OVERWRITE)*
   - **Callers**:
     - `scp/hands/task_kernel_bridge.py:309` calls `heartbeat` at `scp/task_kernel_parts/taskkernel.py:370` (chạy định kỳ trong coroutine `_heartbeat_until_finished` khi action đang thực thi)

2. **`expire_leases`** (`scp/task_kernel_parts/taskkernel.py:395`):
   - Chứa UPDATE:
     - `taskkernel.py:406`: `UPDATE tasks SET state='RECOVERING',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:409`: `UPDATE tasks SET state='HUMAN_REVIEW',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:412`: `UPDATE tasks SET state='QUEUED',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:415`: `UPDATE tasks SET active_lease_id=NULL,... WHERE task_id=? AND version=?`
     - `taskkernel.py:416`: `UPDATE leases SET released=1 WHERE lease_id=?`
     - `taskkernel.py:418`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/api/background_jobs.py:207` calls `expire_leases` at `scp/task_kernel_parts/taskkernel.py:395` (background cronjob `_kernel_lease_expiry_tick`)

3. **`release`** (`scp/task_kernel_parts/taskkernel.py:427`):
   - Chứa UPDATE:
     - `taskkernel.py:441`: `UPDATE leases SET released=1 WHERE lease_id=?`
     - `taskkernel.py:443`: `UPDATE tasks SET active_lease_id=NULL,... WHERE task_id=? AND version=?`
     - `taskkernel.py:448`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/hands/task_kernel_bridge.py:506` calls `release` at `scp/task_kernel_parts/taskkernel.py:427`
     - `scp/hands/task_kernel_bridge.py:664` calls `release` at `scp/task_kernel_parts/taskkernel.py:427` (trong khối `finally`)

---

### 3.3. Nhóm Idempotency (`idempotency_claim`, `idempotency_complete`)

1. **`idempotency_claim`** (Được cài đè tại `scp/task_kernel.py:150` bằng `_idempotency_claim_fenced`):
   - Chứa UPDATE:
     - `task_kernel.py:188`: **`UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?`** *(BLIND OVERWRITE)*
   - **Callers**:
     - `scp/ask_kernel_adapter.py:163` calls `idempotency_claim`
     - `scp/hands/task_kernel_bridge.py:419` calls `idempotency_claim`

2. **`idempotency_complete`** (Được cài đè tại `scp/task_kernel.py:206` bằng `_idempotency_complete_fenced`):
   - Chứa UPDATE:
     - `task_kernel.py:232`: **`UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?`** *(BLIND OVERWRITE)*
   - **Callers**:
     - `scp/hands/task_kernel_bridge.py:520` calls `idempotency_complete`

---

### 3.4. Nhóm Reconcile & Side-Effect Recovery (`record_action_dispatched`, `enter_reconciling`, `reconcile_unknown`, `auto_reconcile_orphans`, `recover_on_boot`)

1. **`record_action_dispatched`** (`scp/task_kernel_parts/taskkernel.py:494`):
   - Chứa UPDATE:
     - `taskkernel.py:530`: `UPDATE tasks SET state='UNKNOWN',version=version+1,... WHERE task_id=? AND version=?`
   - **Callers**:
     - `scp/hands/task_kernel_bridge.py:237` calls `record_action_dispatched` (trước khi bắt đầu gửi side-effect ra external driver)

2. **`enter_reconciling`** (`scp/task_kernel_parts/taskkernel.py:561`):
   - Chứa UPDATE:
     - `taskkernel.py:571`: `UPDATE tasks SET state='RECONCILING',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:576`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `taskkernel.py:578`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/hands/task_kernel_bridge.py:688` calls `enter_reconciling` (trong `reconcile_unknown`)

3. **`reconcile_unknown`** (Được cài đè tại `scp/task_kernel.py:253` bằng `_reconcile_unknown_complete_outcomes`):
   - Chứa UPDATE:
     - `task_kernel.py:293`: **`UPDATE idempotency SET status=?,result_ref=? WHERE logical_key=?`** *(BLIND OVERWRITE)*
     - `task_kernel.py:297`: `UPDATE tasks SET state='HUMAN_REVIEW',version=version+1,... WHERE task_id=? AND version=?`
     - `task_kernel.py:304`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `task_kernel.py:306`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - Hoặc bản gốc tại `scp/task_kernel_parts/taskkernel.py:588` (khi outcome là `NOT_APPLIED`, `APPLIED`, `UNKNOWN`):
     - `taskkernel.py:610, 614, 618`: `UPDATE idempotency SET status=... WHERE logical_key=?`
     - `taskkernel.py:621`: `UPDATE tasks SET state=?,version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:626`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `taskkernel.py:628`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/api/routes/hands_routes.py:175` calls `reconcile_unknown` (POST `/hands/reconcile`)
     - `scp/hands/task_kernel_bridge.py:690` calls `reconcile_unknown`

4. **`auto_reconcile_orphans`** (`scp/task_kernel_parts/taskkernel.py:772`):
   - Chứa UPDATE:
     - `taskkernel.py:829`: `UPDATE tasks SET state=?,version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:842`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `taskkernel.py:845`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/api/background_jobs.py:226` calls `auto_reconcile_orphans` (background cronjob `_kernel_orphan_reconcile_tick`)

5. **`recover_on_boot`** (`scp/task_kernel_parts/taskkernel.py:890`):
   - Chứa UPDATE:
     - `taskkernel.py:918` calls `rebuild_projection(task_id)`
     - `taskkernel.py:923`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `taskkernel.py:925`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
     - `taskkernel.py:927, 930, 933` calls `transition(...)`
   - **Callers**:
     - `scp/api_server_parts/lifespan.py:267` calls `recover_on_boot` (khi FastAPI server khởi động)

---

### 3.5. Nhóm Hoàn Thành & Tiêu Hủy Task (`commit_verification_result`, `commit_completed`, `set_task_kill`, `cancel`)

1. **`commit_completed`** (`scp/task_kernel_parts/taskkernel.py:700`):
   - Chứa UPDATE:
     - `taskkernel.py:719`: `UPDATE tasks SET state='COMPLETED',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:723`: `UPDATE leases SET released=1 WHERE lease_id=?`
     - `taskkernel.py:724`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/task_kernel_parts/taskkernel.py:698` (gọi từ `commit_verification_result`)
     - `scp/ask_kernel_adapter.py:393` calls `commit_verification_result` -> calls `commit_completed`
     - `scp/hands/task_kernel_bridge.py:522` calls `commit_verification_result` -> calls `commit_completed`

2. **`set_task_kill` / `cancel`** (`scp/task_kernel_parts/taskkernel.py:746`):
   - Chứa UPDATE:
     - `taskkernel.py:753`: `UPDATE tasks SET state='CANCELLED',version=version+1,... WHERE task_id=? AND version=?`
     - `taskkernel.py:756`: `UPDATE leases SET released=1 WHERE task_id=?`
     - `taskkernel.py:758`: `UPDATE queue_accounts SET active=active-1 WHERE owner=?`
   - **Callers**:
     - `scp/ask_kernel_adapter.py:228` calls `set_task_kill`
     - `scp/task_kernel_parts/taskkernel.py:770` (`cancel` là alias của `set_task_kill`)
     - Các endpoint quản trị / API routes

---

## 4. Phân Tích Chuyên Sâu Các Điểm Ghi Đè Mù (GAP-02 Vulnerability Analysis)

### Điểm 1: Tử Huyệt `leases` — Hồi Sinh Lease Đã Chết (Heartbeat Resurrection)
- **Vị trí**: `scp/task_kernel_parts/taskkernel.py:388`
- **Mã nguồn hiện tại**:
  ```python
  now = time.time()
  expires = now + extend_seconds
  self.conn.execute('UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?', (now, expires, lease_id))
  ```
- **Cơ chế lỗi**:
  1. Worker 1 nhận `lease_1` cho task `task_A`. Do mạng lag hoặc tác vụ mất nhiều thời gian, lease hết hạn.
  2. Watchdog `expire_leases()` hoặc `auto_reconcile_orphans()` phát hiện lease quá hạn, thực thi:
     `UPDATE leases SET released=1 WHERE lease_id='lease_1'`
     và chuyển `tasks` sang `RECOVERING`.
  3. Worker 2 claim task mới, nhận `lease_2`.
  4. Worker 1 bất ngờ hồi tỉnh (ví dụ từ async sleep), coroutine heartbeat chạy và thực thi:
     `UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id='lease_1'`
  5. Vì câu lệnh UPDATE **chỉ lọc theo `WHERE lease_id=?` mà KHÔNG kiểm tra `version=?` hay `released=0`**, nó âm thầm cập nhật `expires_at` mới cho một lease đã bị thu hồi!
  6. Nếu Worker 1 tiếp tục thực hiện side effect hoặc kiểm tra tính hợp lệ của lease qua DB, lease sẽ xuất hiện như đang hợp lệ (`released` có thể vẫn là 1 nhưng `expires_at` lại trong tương lai, hoặc các truy vấn lọc theo `expires_at > now` bị đánh lừa).

### Điểm 2: Tử Huyệt `idempotency` — Race Condition Đua Nhau Claim (Double-Claim Race)
- **Vị trí**: `scp/task_kernel.py:188` và `scp/task_kernel_parts/taskkernel.py:660`
- **Mã nguồn hiện tại**:
  ```python
  row = self.conn.execute("SELECT * FROM idempotency WHERE logical_key=?", (logical_key,)).fetchone()
  if row:
      if row["status"] == "RETRYABLE":
          self.conn.execute(
              "UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?",
              (logical_key,),
          )
          self._commit()
          return logical_key, True
      self._commit()
      return logical_key, False
  ```
- **Cơ chế lỗi**:
  1. Giả sử tác vụ `step_1` có kết quả trước đó là `NOT_APPLIED` nên trạng thái idempotency là `RETRYABLE`.
  2. Hai worker đồng thời cố gắng thực thi lại tác vụ này. Cả Worker A và Worker B cùng chạy `SELECT * FROM idempotency WHERE logical_key=?`.
  3. Cả 2 đều nhận thấy `status == 'RETRYABLE'`.
  4. Worker A chạy `UPDATE ... SET status='CLAIMED' WHERE logical_key=?` -> commit, trả về `(logical_key, True)`.
  5. Worker B chạy `UPDATE ... SET status='CLAIMED' WHERE logical_key=?` -> commit, cũng trả về `(logical_key, True)`!
  6. **Hậu quả**: Cả 2 worker đều tin rằng mình được độc quyền thực thi hành động! Cả hai cùng dispatch side-effect (ví dụ: chuyển tiền, ghi file, gọi API ngoài), phá hủy hoàn toàn bảo chứng Idempotency!
  7. **Nguyên nhân cốt lõi**: Thiếu `WHERE version=?` (hoặc `WHERE logical_key=? AND status='RETRYABLE'`) và không kiểm tra `rowcount == 1`.

### Điểm 3: Tử Huyệt `idempotency` — Ghi Đè Mù Khi Complete (Blind Completion Overwrite)
- **Vị trí**: `scp/task_kernel.py:232` và `scp/task_kernel_parts/taskkernel.py:687`
- **Mã nguồn hiện tại**:
  ```python
  row = self.conn.execute("SELECT * FROM idempotency WHERE logical_key=?", (logical_key,)).fetchone()
  ...
  self.conn.execute(
      "UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?",
      (result_ref, logical_key),
  )
  ```
- **Cơ chế lỗi**:
  Nếu giữa thời điểm `SELECT` và `UPDATE`, một tiến trình khác (chẳng hạn như reconcile outcome hoặc recovery watchdog) đã cập nhật `idempotency` sang `RECONCILED_APPLIED` hoặc `RETRYABLE`, lệnh `UPDATE` này sẽ **ghi đè mù** lên trạng thái đó mà không phát hiện xung đột version!

### Điểm 4: Tử Huyệt `tasks` — Ghi Đè Mù Khi Task Quá Hạn Trong Queue (`claim_next`)
- **Vị trí**: `scp/task_kernel_parts/taskkernel.py:293`
- **Mã nguồn hiện tại**:
  ```python
  created_at = datetime.fromisoformat(task['created_at']).timestamp()
  if now >= created_at + int(task['deadline_ms']) / 1000.0:
      self.conn.execute("UPDATE tasks SET state='FAILED',version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))
      self._append_event(task['task_id'], 'DEADLINE_EXPIRED', 'QUEUED', 'FAILED', 'kernel', 'queue_deadline_guard', {'deadline_ms': task['deadline_ms']})
      continue
  ```
- **Cơ chế lỗi**:
  Câu lệnh UPDATE ở dòng 293 là câu lệnh duy nhất cập nhật state trong `tasks` mà **hoàn toàn không có `AND version=?`**.
  Nếu một worker khác đang claim task này đồng thời (`claim()` hoặc transition sang `CANCELLED`), lệnh này sẽ đè nát version và trạng thái của worker kia!

---

## 5. Đề Xuất Kế Hoạch Cho Milestone M2 (Exploit Probe) & M3 (OCC Implementation)

### 5.1. Kịch Bản Exploit Probe (Tuân thủ FA-09 cho Milestone M2)
Để chứng minh lỗ hổng trên terminal thực tế trước khi sửa code:
1. **Probe Exploit 1 (Idempotency Double-Claim Race)**:
   - Tạo một bản ghi idempotency với `status='RETRYABLE'`.
   - Chạy 2 tiến trình / luồng giả lập 2 worker cùng claim logical_key đó.
   - Chứng minh cả 2 đều nhận `(key, True)` — vi phạm tính bất biến Idempotency.
2. **Probe Exploit 2 (Lease Heartbeat Zombie Resurrection)**:
   - Khởi tạo task và cấp `lease_1`.
   - Cho lease bị release (`release()` hoặc `expire_leases()`), xác nhận `released=1` trong DB.
   - Gọi `heartbeat(task_id, lease_1)` từ worker cũ.
   - Quan sát thấy `UPDATE leases` thành công và `expires_at` được gia hạn thêm 30s trên một lease đã bị khai tử!

### 5.2. Hướng Dẫn Triển Khai Cho Milestone M3 (Atomic OCC Fencing - INV-01)
1. **Nâng cấp Schema Database**:
   - Thêm cột `version INTEGER NOT NULL DEFAULT 1` vào các bảng:
     - `leases`
     - `idempotency`
     - `control`
   - Cập nhật trong `_schema()` tại `scp/task_kernel_parts/taskkernel.py:54`:
     ```sql
     ALTER TABLE leases ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
     ALTER TABLE idempotency ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
     ALTER TABLE control ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
     ```
2. **Chuẩn hóa Định nghĩa Ngoại Lệ**:
   - Định nghĩa `class OptimisticLockError(KernelError): pass` (hoặc kế thừa / ánh xạ với `StaleLease`).
3. **Cưỡng chế Mệnh Đề `WHERE version=?` Cho Mọi Lệnh UPDATE**:
   - **`leases`**:
     - `heartbeat`: `UPDATE leases SET heartbeat_at=?,expires_at=?,version=version+1 WHERE lease_id=? AND version=? AND released=0` -> Nếu `rowcount != 1` raise `OptimisticLockError("lease heartbeat conflict or already released")`.
     - `release`: `UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND version=? AND released=0`.
   - **`idempotency`**:
     - `idempotency_claim`: Khi claim lại key `RETRYABLE`, thực hiện:
       `UPDATE idempotency SET status='CLAIMED',result_ref=NULL,version=version+1 WHERE logical_key=? AND version=? AND status='RETRYABLE'`
       Nếu `rowcount != 1`, nhận biết ngay có worker khác đã tranh claim trước -> return `(logical_key, False)`.
     - `idempotency_complete`: `UPDATE idempotency SET status='COMPLETED',result_ref=?,version=version+1 WHERE logical_key=? AND version=? AND status='CLAIMED'`
       Nếu `rowcount != 1`, raise `OptimisticLockError("idempotency complete conflict")`.
   - **`tasks`**:
     - Sửa dòng 293 trong `claim_next`: thêm `AND version=?` và kiểm tra `cur.rowcount == 1`.
