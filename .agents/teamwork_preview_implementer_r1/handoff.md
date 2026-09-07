# Handoff Report — Implementer R1: GAP-03 & GAP-04 Remediation

## Execution Context & Metadata
- **HEAD_SHA:** `6070050bdba94b90d8d0d22bbeff7d8e488cd000`
- **TREE_HASH:** `d344024e9214f473787e7cd2085523d761e66dd0`
- **Branch:** `omega/gap-01-remediation`
- **Python Version:** `Python 3.12.10`
- **SQLite Version:** `3.49.1`
- **Working Directory:** `c:\Users\check\Downloads\scp\.agents\teamwork_preview_implementer_r1`

---

## 1. Summary of Changes

### A. `scp/task_kernel_parts/taskkernel.py`
1. **GAP-04: Transaction Boundary Encapsulation (`rebuild_projection`)**:
   - Wrapped the entire method body from the start (`self._begin()`) through validation, read, and write within a single atomic transaction.
   - `self.verify_journal(task_id)` and `self.get_events(task_id)` now run strictly within the transaction boundary, preventing dirty or uncommitted reads across concurrent events.
   - Any failure or mismatch triggers `self._rollback()` in the `except Exception` handler, ensuring fail-closed atomicity.

2. **GAP-03: Optimistic Concurrency Control (OCC) Blind Increment Remediation**:
   - Added `expected_version: int | None = None` parameter to `rebuild_projection()`.
   - Before mutation, reads `task = self._task(task_id)` and derives `cur_version = int(task['version'])`.
   - If `expected_version is not None` and `cur_version != expected_version`, immediately raises `OptimisticLockError(table="tasks", entity_id=task_id, expected_version=expected_version)`.
   - Updated the SQL query from:
     ```sql
     UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=?
     ```
     to:
     ```sql
     UPDATE tasks SET state=?,version=version+1,active_lease_id=?,active_fencing_token=?,updated_at=? WHERE task_id=? AND version=?
     ```
   - Checked `cur.rowcount != 1`; if 0 rows updated, raises `OptimisticLockError(table="tasks", entity_id=task_id, expected_version=target_version)`.
   - Updated placeholder `OptimisticLockError` `__init__` in `taskkernel.py` to accept keyword arguments (`table`, `entity_id`, `expected_version`) for isolated submodule safety.

### B. Verification Assets Added
1. **`tools/probes/probe_gap03_04_blind_overwrite.py`**:
   - FA-09 Exploit Mandate probe script.
   - Subtest 1: Stale `expected_version` rejection.
   - Subtest 2: Concurrent multi-thread rebuild race condition (exactly 1 winner).
   - Subtest 3: Structural SQL `AND version=?` and `self._begin()` transaction boundary inspection.
2. **`tests/T04_kernel/test_rebuild_projection_occ.py`**:
   - 4 regression & adversarial test cases covering happy path, stale version rejection, race condition winner/loser fencing, and journal corruption rollback.

---

## 2. Verification Record

### A. Anti-Placebo Mutation Test (Probe Script)
- **Buggy Baseline Execution:**
  ```text
  python tools/probes/probe_gap03_04_blind_overwrite.py
  Exit Code: 1 (RED)
  Output:
  [PROBE SUBTEST 1] Testing stale version OCC rejection...
    Attempting rebuild_projection with stale expected_version=1 (current=2)...
    [FAIL] rebuild_projection does not accept expected_version
  PROBE FAILED (RED): GAP-03 VULNERABILITY CONFIRMED
  ```
- **Remediated Execution:**
  ```text
  python tools/probes/probe_gap03_04_blind_overwrite.py
  Exit Code: 0 (GREEN)
  Output:
  [PROBE SUBTEST 1] Testing stale version OCC rejection...
    [PASS] OptimisticLockError correctly raised
  [PROBE SUBTEST 2] Testing concurrent rebuild OCC enforcement...
    [PASS] Worker B correctly rejected with OptimisticLockError
  [PROBE SUBTEST 3] Inspecting SQL and Transaction Boundary...
    [PASS] SQL contains 'WHERE task_id=? AND version=?'
    [PASS] Transaction boundary wraps verify_journal and get_events
  ALL OCC AND TRANSACTION INVARIANTS SATISFIED (GREEN)
  ```

### B. Unit & Regression Tests
- **`pytest tests/T04_kernel/test_rebuild_projection_occ.py -v`**:
  `4 passed in 0.60s` (exit 0).
- **`pytest tests/T04_kernel/ -v`**:
  `46 passed in 5.82s` (exit 0) (all existing 42 tests + 4 new tests passed).
- **Full Test Suite `pytest tests/ -q`**:
  `435 passed in 97.29s` (exit 0) (baseline was 431 passed).

### C. Integrity Meta-Audit
- **`python tools/t00_meta_audit.py`**:
  `Exit Code: 0`
  `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`
  Baseline debt preserved without increase; 0 deleted or weakened tests.

---

## 3. Worktree Diff Summary
```diff
--- a/scp/task_kernel_parts/taskkernel.py
+++ b/scp/task_kernel_parts/taskkernel.py
@@ -13,7 +13,24 @@ from scp.kernel_storage import KernelStorage, StorageIntegrityError, make_storag
 
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
+        super().__init__(message)
 
 __all__ = ["TaskKernel", "OptimisticLockError"]
 
@@ -1173,20 +1190,30 @@ class TaskKernel:
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
-        self._begin()
-        try:
+    def rebuild_projection(self, task_id: str, expected_version: int | None = None) -> dict[str, Any]:
+        self._begin()
+        try:
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
@@ -1197,10 +1224,17 @@ class TaskKernel:
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
