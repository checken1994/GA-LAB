# Final Handoff Report — Orchestrator: GAP-03 & GAP-04 Remediation

**Orchestrator**: `teamwork_preview_swe_2`  
**Pattern**: SWE Light (Sequential Refinement Loop)  
**Task**: Vá Tử huyệt số 3 và 4 (GAP-03 + GAP-04) trong `scp/task_kernel_parts/taskkernel.py` theo đúng quy trình Zero-Trust với đầy đủ Adversarial Review và Independent Victory Audit.

---

## 1. Execution Context & Environment Metadata

- **HEAD_SHA:** `6070050bdba94b90d8d0d22bbeff7d8e488cd000`
- **TREE_HASH:** `d344024e9214f473787e7cd2085523d761e66dd0`
- **WORKTREE:** `C:\Users\check\Downloads\scp`
- **Python Version:** `Python 3.12.10`
- **SQLite Version:** `3.49.1`
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\teamwork_preview_swe_2`

---

## 2. Observation (Problem Definition & Target Scope)

- **Target File**: `scp/task_kernel_parts/taskkernel.py`
- **Target Function**: `rebuild_projection()` (around lines ~1192-1230)
- **GAP-03 (Blind Version Increment - CRITICAL)**:
  - Previously, `rebuild_projection()` executed:
    `UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=?`
  - The query lacked `AND version=?` and did not verify `cur.rowcount == 1`.
  - Concurrency Hazard: Two concurrent workers or callers could clobber each other's projection state, violating monotonic version ordering and optimistic locking guarantees.
- **GAP-04 (rebuild_projection Transaction Boundary - HIGH)**:
  - Previously, `verify_journal()` and `get_events()` executed outside `self._begin()`.
  - Concurrency Hazard: External writes could commit between event reading and projection update (TOCTOU race), leaving the task projection in an inconsistent or stale state. Additionally, failures did not guarantee atomic rollback.

---

## 3. Logic Chain (SWE Light Refinement Progression)

The remediation followed the SWE Light sequential refinement loop with 3 deep adversarial review rounds and an independent victory audit:

### Round 1 — `teamwork_preview_implementer` (Conv ID: `45918407-26be-4e3b-a818-0ded1d241355`)
- Added `expected_version: int | None = None` parameter to `rebuild_projection()`.
- Implemented active version lookup `cur_version = int(task['version'])` and version verification before update.
- Updated SQL query to `WHERE task_id=? AND version=?`, verified `cur.rowcount == 1`, and raised `OptimisticLockError` on mismatch.
- Encapsulated entire `rebuild_projection()` body within `self._begin()`, `self._commit()`, and fail-closed `self._rollback()`.
- Created probe script `tools/probes/probe_gap03_04_blind_overwrite.py` and unit tests in `tests/T04_kernel/test_rebuild_projection_occ.py`.

### Round 2 — `teamwork_preview_reviewer` (Adversarial Round 1, Conv ID: `11402df3-345a-4d03-8d25-d18c9988f5f6`)
- Detected fake concurrency in initial probe Subtest 2 (sequential execution masquerading as concurrency) and refactored it to spawn 2 genuine OS threads with `threading.Barrier(2)`.
- Added Subtest 4 for runtime transaction rollback verification.
- Added cross-method OCC race tests (`transition()` vs `rebuild_projection()`) and 10-thread concurrency barrier test in `test_rebuild_projection_occ.py` (expanded to 7 tests).

### Round 3 — `teamwork_preview_reviewer` (Adversarial Round 2, Conv ID: `063a6411-5092-478c-9b4d-18411d9090e5`)
- Uncovered a placebo assertion in Probe Subtest 4 (which passed on buggy code because `KernelError` happened before `_begin()`). Upgraded Subtest 4 to dynamically track `in_transaction == True` during `get_events()`, making it strictly fail RED on buggy code and pass GREEN on fixed code.
- Identified unverified multi-process SQLite WAL contention; added `test_rebuild_projection_multiprocess_concurrency_single_winner` using 4 independent OS processes (`multiprocessing.Process`).
- Synchronized `OptimisticLockError` placeholder attributes in `taskkernel.py`. Test suite expanded to 9 tests.

### Round 4 — `teamwork_preview_reviewer` (Adversarial Round 3, Conv ID: `35a2c3d5-da95-4f32-a136-a4668e08460e`)
- Identified untested lease lifecycle persistence: added `test_rebuild_projection_lease_lifecycle_and_terminal_states` verifying active lease preservation, released lease clearing, terminal state preservation, and negative version rejection (`expected_version=-1`).
- Empirically validated anti-placebo sensitivity against 3 distinct historic buggy permutations (all tripped into RED; fixed code GREEN). Test suite expanded to 10 tests.

### Independent Orchestrator Verification
- Personally inspected diff of `scp/task_kernel_parts/taskkernel.py`.
- Personally executed:
  1. `python tools/probes/probe_gap03_04_blind_overwrite.py` -> Exit 0 (all 4 subtests PASS).
  2. `pytest tests/T04_kernel/test_rebuild_projection_occ.py -v` -> Exit 0 (10 passed in 1.75s).
  3. `python tools/t00_meta_audit.py` -> Exit 0 (All integrity checks passed; 0 new regressions).
  4. `pytest tests/ -q` -> Exit 0 (441 passed in 121.57s; baseline 431, +10 new tests, ≥ 430 satisfied).

### Round 5 — `teamwork_preview_victory_auditor` (Conv ID: `14129dce-59a1-40c8-b091-d723b16996a8`)
- Conducted independent 3-phase audit (Timeline, Cheating Detection FA-01 to FA-10, Independent Test Execution).
- Confirmed zero cheating, zero assertion loosening, clean fail-closed OCC boundaries at SQLite level.
- **VERDICT: VICTORY CONFIRMED**.

---

## 4. Verification Record & Evidence

| Verification Target | Command | Output / Status | Exit Code |
|---------------------|---------|-----------------|-----------|
| **FA-09 Probe** | `python tools/probes/probe_gap03_04_blind_overwrite.py` | Subtest 1: Stale version OCC rejection PASS<br>Subtest 2: True parallel threads barrier race PASS<br>Subtest 3: Structural SQL check PASS<br>Subtest 4: Anti-placebo transaction boundary tracking PASS | **0** |
| **Target OCC Tests** | `pytest tests/T04_kernel/test_rebuild_projection_occ.py -v` | 10 passed in 1.75s | **0** |
| **Meta-Audit Gate** | `python tools/t00_meta_audit.py` | All integrity checks passed (0 new regressions) | **0** |
| **Full Test Suite** | `pytest tests/ -q` | 441 passed in 121.57s (Requirement ≥ 430 met) | **0** |

---

## 5. Worktree Changes (`git diff`)

```diff
--- a/scp/task_kernel_parts/taskkernel.py
+++ b/scp/task_kernel_parts/taskkernel.py
@@ -13,7 +13,26 @@ from scp.kernel_storage import KernelStorage, StorageIntegrityError, make_storag
 
 class OptimisticLockError(RuntimeError):
     """Placeholder overwritten by scp.task_kernel.OptimisticLockError upon import."""
-    pass
+
+    def __init__(
+        self,
+        message: str = "",
+        *,
+        table: str | None = None,
+        entity_id: str | None = None,
+        expected_version: int | None = None,
+    ) -> None:
+        self.table = table
+        self.entity_id = entity_id
+        self.expected_version = expected_version
+        if not message:
+            message = (
+                f"Optimistic lock conflict on table '{table}' for entity '{entity_id}'"
+                f" (expected version {expected_version})"
+            )
+        elif entity_id and entity_id not in message:
+            message = f"{message} (table={table}, entity_id={entity_id}, expected_version={expected_version})"
+        super().__init__(message)
 
 __all__ = ["TaskKernel", "OptimisticLockError"]
 
@@ -1173,20 +1192,30 @@ class TaskKernel:
             prev = e['event_hash']
         return {'task_id': task_id, 'event_count': len(events), 'hash_chain_valid': not errors, 'errors': errors}
 
-    def rebuild_projection(self, task_id: str) -> dict[str, Any]:
-        journal = self.verify_journal(task_id)
-        if not journal['hash_chain_valid']:
-            details = ';'.join(journal['errors'])
-            raise KernelError(f'journal integrity invalid: {details}')
-        events = self.get_events(task_id)
-        if not events:
-            raise NotFound(task_id)
-        state = events[0]['to_state']
-        for event in events[1:]:
-            if event['to_state']:
-                state = event['to_state']
+    def rebuild_projection(self, task_id: str, expected_version: int | None = None) -> dict[str, Any]:
         self._begin()
         try:
+            journal = self.verify_journal(task_id)
+            if not journal['hash_chain_valid']:
+                details = ';'.join(journal['errors'])
+                raise KernelError(f'journal integrity invalid: {details}')
+            events = self.get_events(task_id)
+            if not events:
+                raise NotFound(task_id)
+            state = events[0]['to_state']
+            for event in events[1:]:
+                if event['to_state']:
+                    state = event['to_state']
+            task = self._task(task_id)
+            cur_version = int(task['version'])
+            if expected_version is not None and cur_version != expected_version:
+                raise OptimisticLockError(
+                    f"concurrency conflict rebuilding projection for task {task_id}: expected version {expected_version}, found {cur_version}",
+                    table="tasks",
+                    entity_id=task_id,
+                    expected_version=expected_version,
+                )
+            target_version = expected_version if expected_version is not None else cur_version
             if state in {"LEASED", "RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN"}:
                 lease_row = self.conn.execute(
                     'SELECT lease_id, fencing_token FROM leases WHERE task_id=? AND released=0 ORDER BY fencing_token DESC LIMIT 1',
@@ -1197,10 +1226,17 @@ class TaskKernel:
             else:
                 active_lease_id = None
                 active_fencing_token = 0
-            self.conn.execute(
-                'UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=?',
-                (state, active_lease_id, active_fencing_token, now_iso(), task_id),
+            cur = self.conn.execute(
+                'UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=? AND version=?',
+                (state, active_lease_id, active_fencing_token, now_iso(), task_id, target_version),
             )
+            if cur.rowcount != 1:
+                raise OptimisticLockError(
+                    f"concurrency conflict rebuilding projection for task {task_id}: expected version {target_version}",
+                    table="tasks",
+                    entity_id=task_id,
+                    expected_version=target_version,
+                )
             self._commit()
         except Exception:
             self._rollback()
```

---

## 6. Caveats & Open Issues Ledger

- **Item 1 (High Concurrency OS Pressure)**: High concurrency stress (>50 parallel OS processes) contending on `rebuild_projection` simultaneously remains bounded by SQLite's single-writer architecture. Under prolonged extreme write contention exceeding 25 retries (>5s sustained write lock hold), SQLite returns `OperationalError: database is locked`.
- **Item 2 (Missing Task Row vs Journal Recreation)**: If `rebuild_projection()` is called on a task whose row was manually deleted from SQLite `tasks` table, it raises `NotFound(task_id)` upon `self._task(task_id)` instead of reconstructing an initial row from `TASK_CREATED` event. This is consistent with current architecture where `tasks` must already exist.
- **Item 3 (Network Filesystems)**: Network-mounted filesystems (NFS/SMB) violate POSIX/Win32 mandatory lock semantics and are not recommended for SQLite multi-process WAL databases.

---

## 7. Conclusion

Vá Tử huyệt số 3 (GAP-03: Blind Version Increment) và Tử huyệt số 4 (GAP-04: rebuild_projection Transaction Boundary) trong `scp/task_kernel_parts/taskkernel.py` đã hoàn tất thắng lợi:
1. Cơ chế Optimistic Concurrency Control (OCC) được thực thi nghiêm ngặt tại tầng SQLite Engine (`WHERE task_id=? AND version=?` và `cur.rowcount == 1`), ném `OptimisticLockError` khi phát hiện tranh chấp.
2. Toàn bộ `rebuild_projection()` được bao bọc an toàn trong transaction (`self._begin()`, `self._commit()`, `self._rollback()`), triệt tiêu hoàn toàn rủi ro TOCTOU desynchronization giữa journal và projection.
3. Bài probe FA-09 chống giả dược (Anti-Placebo) đã chứng minh độ nhạy phân biệt rõ ràng: Đỏ trên code lỗi, Xanh trên code đã sửa.
4. Toàn bộ 441 bài kiểm thử pytest và T00 Meta-Audit đều vượt qua (Exit 0).
5. Independent Victory Auditor đã xác nhận kết quả với phán quyết **VICTORY CONFIRMED**.
