# TaskKernel Failure Boundary & `commit_failed()` Implementation Specification Report

**Document:** `c:\Users\check\Downloads\scp\.agents\explorer_1\handoff.md`  
**Author:** Explorer 1 (`teamwork_preview_explorer`)  
**Target:** TaskKernel Core Implementation (`scp/task_kernel_parts/taskkernel.py`, `scp/task_kernel.py`)  
**Scope:** Milestone M1 — GAP-12 Remediation Exploration & Blueprint  
**Authority:** `GA.md`, `.agents/AGENTS.md` (FA-01 through FA-13), `.agents/skills/scp-dna/SKILL.md`, `.agents/skills/scp-task-kernel-review/SKILL.md`  
**Timestamp:** 2026-09-08T01:30:00Z  

---

## 1. Observation

### 1.1 `scp/task_kernel_parts/taskkernel.py:250-256` — State Transition Guard Asymmetry
Direct inspection of `scp/task_kernel_parts/taskkernel.py` lines 250–256 shows:
```python
250:     ) -> dict[str, Any]:
251:         if to_state not in STATES and to_state != "WAITING_APPROVAL":
252:             raise InvalidTransition(f"unknown target state {to_state}")
253:         if to_state == "COMPLETED":
254:             raise InvalidTransition(
255:                 "direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence"
256:             )
```
- **Observed:** `to_state == "COMPLETED"` is guarded and raises `InvalidTransition`. However, `to_state == "FAILED"` is completely unguarded.
- **Consequence:** Calling `kernel.transition(task_id, "FAILED", ...)` proceeds down to line 268 (`self._task(task_id)`), line 278 (checks `to_state in ALLOWED_TRANSITIONS[old]`), line 347 (`UPDATE tasks SET state='FAILED'`), and line 359 (appends `STATE_TRANSITION` event).

### 1.2 `scp/task_kernel_parts/taskkernel.py:464-480` — `_assert_lease()` Signature and Validation
Direct inspection of `_assert_lease()` shows:
```python
464:     def _assert_lease(self, lease_id: str, task_id: str) -> Any:
465:         lease = self._lease(lease_id)
466:         control = self._control()
467:         now = time.time()
468:         if lease['task_id'] != task_id or lease['released'] or lease['expires_at'] <= now or (lease['global_kill_epoch'] != control['global_kill_epoch']) or control['global_kill']:
469:             if lease['released']:
470:                 raise OptimisticLockError(
471:                     f"lease {lease_id} has already been released",
472:                     table="leases",
473:                     entity_id=lease_id,
474:                 )
475:             raise StaleLease(lease_id)
476:         latest = self.conn.execute('SELECT COALESCE(MAX(fencing_token), 0) AS n FROM leases WHERE task_id=?', (task_id,)).fetchone()['n']
477:         if int(lease['fencing_token']) != int(latest):
478:             raise StaleLease(lease_id)
479:         return lease
```
- **Observed:** The parameters are `(self, lease_id: str, task_id: str)`.
- **Observed:** `_lease(lease_id)` retrieves `SELECT * FROM leases WHERE lease_id=?`, which returns columns: `lease_id, task_id, attempt_id, worker_id, issued_at, expires_at, heartbeat_at, fencing_token, global_kill_epoch, released, version`.
- **Observed:** `_assert_lease()` verifies `task_id`, `released`, `expires_at`, `global_kill_epoch`, `global_kill`, and `fencing_token`. It **NEVER** compares the caller's identity (`actor`) against `lease['worker_id']`.

### 1.3 `tasks` and `leases` Table Schemas via PRAGMA Inspection
Live execution of `PRAGMA table_info(tasks)`:
```text
Columns in tasks:
['task_id', 'owner', 'goal', 'risk_tier', 'deadline_ms', 'max_attempts', 'input_hash', 'priority', 'state', 'version', 'active_lease_id', 'active_fencing_token', 'created_at', 'updated_at']
```
- **Observed:** The `tasks` table contains `max_attempts INTEGER NOT NULL` (default 3), but currently has **NO** `attempts` column and **NO** `error` column.
- **Observed in `taskkernel.py:167-181`:** Schema evolution is implemented via:
  ```python
  task_columns = {row['name'] for row in self.conn.execute('PRAGMA table_info(tasks)').fetchall()}
  if 'priority' not in task_columns:
      self.conn.execute('ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 5')
  if 'active_lease_id' not in task_columns:
      self.conn.execute('ALTER TABLE tasks ADD COLUMN active_lease_id TEXT')
  if 'active_fencing_token' not in task_columns:
      self.conn.execute('ALTER TABLE tasks ADD COLUMN active_fencing_token INTEGER NOT NULL DEFAULT 0')
  if 'version' not in task_columns:
      self.conn.execute('ALTER TABLE tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
  ```
  Adding `attempts INTEGER NOT NULL DEFAULT 0` and `error TEXT` via this exact mechanism ensures zero schema migration friction.

### 1.4 Downstream Callers of `transition(..., "FAILED")` Across Codebase
Live AST/Regex scan across `scp/` and `tests/`:
1. `scp/ask_kernel_adapter.py:430`:
   ```python
   def fail(self, task: dict[str, Any], reason: str) -> None:
       ...
       self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)
   ```
2. `scp/hands/task_kernel_bridge.py:445` & `582`:
   ```python
   # Line 445:
   self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", reason="hands_policy_denied_before_dispatch", payload={"action": action})
   # Line 582:
   self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", reason="hands_bridge_pre_dispatch_failure", payload={"errorType": type(exc).__name__})
   ```
3. `tests/`: **ZERO** test files directly invoke `kernel.transition(..., "FAILED")`.
   `tests/T04_kernel/test_adversarial_kernel_flaws.py:890` invokes `adapter.fail(task1, reason=...)` which will route cleanly to `commit_failed()`.

### 1.5 Baseline Test Suite Status
Running `pytest tests/T04_kernel -q`:
```text
78 passed in 7.28s (exit code: 0)
```
Existing kernel tests are 100% GREEN.

---

## 2. Logic Chain

```
[Observation 1.1] ──> Line 253 checks only 'to_state == "COMPLETED"'; 'FAILED' is unguarded.
         │
         ▼
[Inference 2.1]  ──> Extending guard to `if to_state in ("COMPLETED", "FAILED"): raise InvalidTransition(...)`
                     unconditionally blocks all 4 exploit vectors identified in GAP-12 Delta Audit.
         │
         ▼
[Observation 1.4] ──> Only AskKernelAdapter and TaskKernelBridge call transition(..., "FAILED").
                     No tests in tests/ call it directly. Blocking direct FAILED breaks zero existing tests,
                     and only requires updating the two known callers to use commit_failed().
         │
         ▼
[Observation 1.2] ──> _assert_lease(lease_id, task_id) does not check lease_row["worker_id"] == actor.
         │
         ▼
[Inference 2.2]  ──> Adding `actor: str | None = None` to `_assert_lease(lease_id, task_id, actor=None)`:
                     - Preserves 100% backward compatibility for existing callers.
                     - When actor is provided, asserts `lease["worker_id"] == actor`.
                     - Rejects stolen lease attacks with StaleLease.
         │
         ▼
[Observation 1.3] ──> tasks table has max_attempts, but lacks attempts and error columns.
         │
         ▼
[Inference 2.3]  ──> In `_schema()`, add ALTER TABLE tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0,
                     and ALTER TABLE tasks ADD COLUMN error TEXT.
                     In commit_failed(), fetch current attempts and compare against max_attempts.
                     If failure is RETRYABLE and new_attempts < max_attempts:
                         target_state = "RETRY_SCHEDULED" (or "UNKNOWN" if uncertain side effect)
                     Else:
                         target_state = "FAILED"
```

---

## 3. Caveats

1. **Argument Order in `_assert_lease`:** The existing internal method is `_assert_lease(self, lease_id: str, task_id: str)`. In some prompt descriptions, this was written colloquially as `_assert_lease(task_id, lease_id, actor=actor)`. The implementer must keep `lease_id` as the first argument to avoid breaking existing callers at lines 324, 327, 484, 514, 590, 640, 678, 924.
2. **Actor Mismatch in `TaskKernelBridge`:** In `TaskKernelBridge`, the lease was claimed with `self.worker_id` (`"hands-route-worker"` by default), but lines 451 and 588 passed `actor="hands-kernel-bridge"`. When migrating to `commit_failed()`, `actor=self.worker_id` must be passed so it matches the lease's `worker_id`.
3. **Actor Mismatch in `AskKernelAdapter`:** In `AskKernelAdapter.begin()`, line 161 claims the lease with worker `"ask-route-worker"`. When `AskKernelAdapter.fail()` calls `commit_failed()`, `actor="ask-route-worker"` must be passed to match the lease.
4. **State Machine Transitions from `RETRY_SCHEDULED`:** In `task_kernel.py:38`, `ALLOWED_TRANSITIONS["RETRY_SCHEDULED"] = {"QUEUED", "FAILED", "CANCELLED"}`. Moving to `RETRY_SCHEDULED` allows the task to be re-queued when backoff expires, without violating the state machine invariants.

---

## 4. Conclusion & Concrete Implementation Specification

### 4.1 Transition Guard Extension (`scp/task_kernel_parts/taskkernel.py:253-256`)
Replace lines 253–256 with:
```python
        if to_state in ("COMPLETED", "FAILED"):
            raise InvalidTransition(
                f"direct transition to {to_state} is forbidden; use commit_{to_state.lower()}() with valid evidence"
            )
```

### 4.2 `_assert_lease()` Update (`scp/task_kernel_parts/taskkernel.py:464-480`)
Update signature and add actor verification:
```python
    def _assert_lease(self, lease_id: str, task_id: str, actor: str | None = None) -> Any:
        lease = self._lease(lease_id)
        control = self._control()
        now = time.time()
        if lease['task_id'] != task_id or lease['released'] or lease['expires_at'] <= now or (lease['global_kill_epoch'] != control['global_kill_epoch']) or control['global_kill']:
            if lease['released']:
                raise OptimisticLockError(
                    f"lease {lease_id} has already been released",
                    table="leases",
                    entity_id=lease_id,
                )
            raise StaleLease(lease_id)
        latest = self.conn.execute('SELECT COALESCE(MAX(fencing_token), 0) AS n FROM leases WHERE task_id=?', (task_id,)).fetchone()['n']
        if int(lease['fencing_token']) != int(latest):
            raise StaleLease(lease_id)
        if actor is not None and str(actor).strip():
            if lease['worker_id'] != str(actor).strip():
                raise StaleLease(f"actor '{actor}' does not match lease worker '{lease['worker_id']}'")
        return lease
```

### 4.3 Schema Migration in `_schema()` (`scp/task_kernel_parts/taskkernel.py:167-181`)
Add columns to `tasks`:
```python
        if 'attempts' not in task_columns:
            self.conn.execute('ALTER TABLE tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0')
        if 'error' not in task_columns:
            self.conn.execute('ALTER TABLE tasks ADD COLUMN error TEXT')
```
And in `CREATE TABLE IF NOT EXISTS tasks`, include:
```sql
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
```

### 4.4 `commit_failed()` Implementation Specification (`scp/task_kernel_parts/taskkernel.py`)
Add method to `TaskKernel`:
```python
    def commit_failed(
        self,
        task_id: str,
        lease_id: str,
        actor: str,
        failure_classification: str,
        indictment_ref: str,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Commit an authenticated, verified failure or route to retry/recovery.
        
        Enforces:
        - Strict lease validity and worker actor ownership matching.
        - Non-empty failure classification and verifiable indictment reference.
        - Retry budget preservation: if failure is retryable and attempts < max_attempts,
          transitions to RETRY_SCHEDULED (or UNKNOWN); otherwise transitions to FAILED.
        - Atomic SQLite persistence: updates tasks, appends immutable journal event,
          releases lease, and decrements queue active count with OCC version checks.
        """
        if not task_id or not str(task_id).strip():
            raise KernelError("task_id is required")
        if not lease_id or not str(lease_id).strip():
            raise StaleLease("lease_id is required")
        if not actor or not str(actor).strip():
            raise KernelError("actor is required")
        if not failure_classification or not str(failure_classification).strip():
            raise KernelError("failure_classification is required")
        if not indictment_ref or not str(indictment_ref).strip():
            raise KernelError("indictment_ref is required; failure commitment requires verifiable failure evidence")

        self._begin()
        try:
            # 1. Assert lease validity and actor ownership
            lease = self._assert_lease(lease_id, task_id, actor=actor)
            task = self._task(task_id)

            old_state = task["state"]
            if old_state in TERMINAL:
                raise InvalidTransition("terminal task is immutable")
            if old_state not in {"RUNNING", "WAITING_TOOL", "VERIFYING", "LEASED", "CHECKPOINTED", "UNKNOWN"}:
                raise InvalidTransition(f"{old_state}->commit_failed")
            if task["active_lease_id"] != lease_id:
                raise StaleLease(f"failure lease {lease_id} does not match active task lease {task['active_lease_id']}")

            is_system = getattr(self, "_system_authority", False)
            bound = getattr(self, "_bound_leases", {}).get(task_id)
            if not is_system:
                if not bound:
                    raise StaleLease(f"kernel instance does not possess active lease authority to fail task {task_id}")
                if bound != lease_id:
                    raise StaleLease(f"caller lease {lease_id} does not match bound instance lease {bound}")

            # 2. Retry budget & failure classification evaluation
            cur_version = int(task["version"])
            current_attempts = int(task["attempts"]) if ("attempts" in task.keys() and task["attempts"] is not None) else 0
            max_attempts = int(task["max_attempts"]) if ("max_attempts" in task.keys() and task["max_attempts"] is not None) else 3
            new_attempts = current_attempts + 1

            classification_upper = failure_classification.strip().upper()
            retryable_classes = {"RETRYABLE", "TRANSIENT", "TIMEOUT", "NETWORK_ERROR", "TEMPORARY"}
            uncertain_classes = {"UNKNOWN", "UNCERTAIN", "LOST_RESPONSE", "CRASH_AFTER_SUBMIT"}

            if classification_upper in uncertain_classes:
                target_state = "UNKNOWN"
                event_type = "TASK_UNKNOWN_STATE"
                reason = f"uncertain_state:{classification_upper.lower()}"
            elif (classification_upper in retryable_classes) and (new_attempts < max_attempts):
                target_state = "RETRY_SCHEDULED"
                event_type = "TASK_RETRY_SCHEDULED"
                reason = f"retryable_failure:{classification_upper.lower()}"
            else:
                target_state = "FAILED"
                event_type = "TASK_FAILED"
                reason = f"terminal_failure:{classification_upper.lower()}"

            # 3. Serialize error details for storage
            error_payload = {
                "classification": classification_upper,
                "indictment_ref": indictment_ref,
                "details": details or {},
                "attempts": new_attempts,
                "max_attempts": max_attempts,
            }
            error_json = json.dumps(error_payload, ensure_ascii=False, sort_keys=True)

            # 4. Atomic OCC update to tasks
            cur = self.conn.execute(
                "UPDATE tasks SET state=?,attempts=?,error=?,version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=? AND version=?",
                (target_state, new_attempts, error_json, now_iso(), task_id, cur_version),
            )
            if cur.rowcount != 1:
                raise OptimisticLockError(
                    f"concurrency conflict failing task {task_id}: expected version {cur_version}",
                    table="tasks",
                    entity_id=task_id,
                    expected_version=cur_version,
                )

            # 5. Append immutable event journal entry
            event_payload = {
                "lease_id": lease_id,
                "actor": actor,
                "failure_classification": classification_upper,
                "indictment_ref": indictment_ref,
                "details": details or {},
                "attempts": new_attempts,
                "max_attempts": max_attempts,
            }
            self._append_event(
                task_id,
                event_type,
                old_state,
                target_state,
                actor,
                reason,
                payload=event_payload,
            )

            # 6. Release active lease and decrement queue quota
            self.conn.execute(
                "UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0",
                (lease_id,),
            )
            self.conn.execute(
                "UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END,version=version+1 WHERE owner=?",
                (task["owner"],),
            )
            if hasattr(self, "_bound_leases"):
                self._bound_leases.pop(task_id, None)

            self._commit()
            return self.get_task(task_id)
        except Exception:
            self._rollback()
            raise
```

### 4.5 Downstream Caller Migration Specifications

#### `scp/ask_kernel_adapter.py:426-440`
```python
    def fail(self, task: dict[str, Any], reason: str, failure_classification: str = "FATAL", details: dict[str, Any] | None = None) -> None:
        try:
            task_id = task["task_id"]
            current = self.kernel.get_task(task_id)
            if current["state"] not in _TERMINAL:
                lease_id = task.get("lease_id")
                if lease_id:
                    indictment_ref = f"ask://{task_id}/fail/{hashlib.sha256(reason.encode('utf-8')).hexdigest()[:16]}"
                    self.kernel.commit_failed(
                        task_id=task_id,
                        lease_id=lease_id,
                        actor="ask-route-worker",
                        failure_classification=failure_classification,
                        indictment_ref=indictment_ref,
                        details={"reason": reason, **(details or {})},
                    )
                else:
                    self.kernel.set_task_kill(task_id, actor="ask-kernel-adapter")
            with _TRACE_LOCK:
                self.trace.append(
                    task_id=task_id,
                    attempt_id=task.get("attempt_id"),
                    lease_id=task.get("lease_id"),
                    checkpoint_id=task.get("checkpoint_id"),
                    outcome="FAILED",
                    reason=reason,
                )
        except Exception as exc:  # non-fatal audit fallback; original error wins
            try:
                from scp.core.exception_policy import observe_nonfatal

                observe_nonfatal(component="scp/ask_kernel_adapter.py:fail", exception_type=type(exc).__name__)
            except Exception:
                return
```

#### `scp/hands/task_kernel_bridge.py:443-460` and `578-598`
- At line 443:
```python
            if self._policy_blocked_before_dispatch(result):
                self.kernel.commit_failed(
                    task_id=task_id,
                    lease_id=lease.lease_id,
                    actor=self.worker_id,
                    failure_classification="POLICY_DENIED",
                    indictment_ref=self._evidence_ref(task_id, result),
                    details={"action": action, "reason": "hands_policy_denied_before_dispatch"},
                )
                lease_active = False
```
- At line 578:
```python
            try:
                if lease_id and lease_active:
                    self.kernel.commit_failed(
                        task_id=task_id,
                        lease_id=lease_id,
                        actor=self.worker_id,
                        failure_classification="FATAL",
                        indictment_ref=f"hands://{task_id}/error/{type(exc).__name__}",
                        details={"errorType": type(exc).__name__, "reason": "hands_bridge_pre_dispatch_failure"},
                    )
            except Exception:
                pass
```

---

## 5. Verification Method

To independently verify this specification once implemented:

1. **Verify GAP-12 Deterministic Probe Transitions from RED to GREEN:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   *Pass criteria:* Exit code 0, all 4 vectors report `PROTECTED_GREEN_InvalidTransition`, verdict `ALL_VECTORS_PROTECTED_GREEN`.

2. **Verify Challenger Stress Test:**
   ```powershell
   python tools/probes/stress_test_gap12_downstream_and_probe.py
   ```
   *Pass criteria:* Exit code 0.

3. **Verify Kernel Test Suite Integrity:**
   ```powershell
   pytest tests/T04_kernel --basetemp=reports/tmp_t04_verify -q
   ```
   *Pass criteria:* 78 passed in ~7s, exit code 0.

4. **Verify Direct Transition to FAILED is Blocked (Interactive One-Liner):**
   ```powershell
   python -c "from scp.task_kernel import TaskKernel, InvalidTransition; import tempfile; k = TaskKernel(tempfile.mktemp('.sqlite3')); k.create_task('t1', 'o1', 'g1'); k.transition('t1', 'PLANNING'); (lambda: None)() if (try_block := False) else None; ...'
   ```
   Calling `k.transition('t1', 'FAILED')` must raise `InvalidTransition`.
