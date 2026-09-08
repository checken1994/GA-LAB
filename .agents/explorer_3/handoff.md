# SCP Explorer 3 Comprehensive Investigation Report: Test Suites, Probes, FA-12 Empirical Closure & FA-13 Causal Coverage

- **Role:** Explorer 3 (`teamwork_preview_explorer`)
- **Authority:** `.agents/skills/scp-dna/SKILL.md`, `.agents/skills/scp-reality-verifier/SKILL.md`, `.agents/AGENTS.md` (FA-01 through FA-13)
- **Parent / Orchestrator Conversation ID:** `f1e50da6-b37c-427b-a8a3-fdc334188734`
- **Target Vulnerability:** GAP-12 (`TaskKernel` State Machine Terminal `FAILED` Boundary & Failure Handling)
- **Scope & Mode:** READ-ONLY Exploration (Zero code modifications in `scp/` or `tests/`)
- **Date / Timestamp:** 2026-09-08T08:31:00+07:00

---

## 1. Observation

### 1.1 Probe Analysis: `tools/probes/probe_gap12_delta_audit.py`
Direct inspection and live terminal execution of `tools/probes/probe_gap12_delta_audit.py` revealed the exact mechanics of the probe and its anti-placebo evaluation contract:

```powershell
python tools/probes/probe_gap12_delta_audit.py
```

Output:
```text
================================================================================
SCP-OMEGA DELTA AUDIT: GAP-12 EMPIRICAL PROBE
Subsystem: TaskKernel State Machine
Invariants Tested:
  - INV-GAP12-01: Prohibition of Raw Unverified Transition to Terminal FAILED
  - INV-GAP12-02: Mandatory Indictment & Evidence for Failure Commitment
  - INV-GAP12-03: Preservation of Retry Budget and Recovery Routing
  - INV-GAP12-04: System Authority Separation for Pre-execution Indictment
================================================================================
...
PROBE RESULTS SUMMARY & ANTI-PLACEBO CONTRACT EVALUATION
================================================================================
  VECTOR_1: PLANNING -> FAILED (Unauthenticated, No Lease, No Evidence)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_2: RUNNING -> FAILED (No Crash Evidence / Zero Indictment)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_3: VERIFYING -> FAILED (Verifier Check Bypassed)
    Verdict: VULNERABILITY_PROVEN_RED
  VECTOR_4: Stolen Lease Sabotage (Recovery Machine Bypassed)
    Verdict: VULNERABILITY_PROVEN_RED

Anti-Placebo Contract Status:
  >> RED STATE CONFIRMED: All 4 exploit vectors succeed on current codebase.
  >> Vulnerability GAP-12 is actively exploitable at the database layer.
  >> Verdict: ALL_VECTORS_PROVEN_RED
================================================================================
Exit code: 0
```

#### Vector Mechanics in Probe:
1. **Vector 1: `PLANNING -> FAILED` (lines 78–109):**
   - Task `t1_id = "task_gap12_v1"` is transitioned from `CREATED` to `PLANNING`. `active_lease_id` is `None`.
   - Caller invokes `kernel.transition(t1_id, "FAILED", actor="unauthenticated_attacker_v1", reason="arbitrary_external_cancellation_without_proof")`.
   - *Current Code Result:* In `scp/task_kernel_parts/taskkernel.py:253`, line checks only `if to_state == "COMPLETED"`; `FAILED` is unguarded. In line 310, `is_leased_state` is False, `active_lease_id` is None, so lease check is completely bypassed (`token = 0`). Task state mutates to `FAILED` in SQLite (`VULNERABILITY_PROVEN_RED`).
   - *Expected Protected Behavior:* Must raise `InvalidTransition`. Probe catches `InvalidTransition` and records `status = "PROTECTED_GREEN_InvalidTransition"`.

2. **Vector 2: `RUNNING -> FAILED` (lines 114–150):**
   - Task `t2_id = "task_gap12_v2"` created with `max_attempts=3`, transitions to `PLANNING -> READY -> QUEUED`, claimed by `worker_beta` and started into `RUNNING`.
   - Worker invokes `kernel.transition(t2_id, "FAILED", lease_id=l2.lease_id, actor="worker_beta", reason="unverified_worker_crash_claim")`.
   - *Current Code Result:* Succeeds immediately on attempt 1 of 3 without verifying error classification or crash dump. Remaining retry attempts are destroyed; task is locked in immutable `FAILED` (`VULNERABILITY_PROVEN_RED`).
   - *Expected Protected Behavior:* Direct transition raises `InvalidTransition`. Failure commitment must route through `commit_failed()`. When caught, probe records `status = "PROTECTED_GREEN_InvalidTransition"`.

3. **Vector 3: `VERIFYING -> FAILED` (lines 155–192):**
   - Task `t3_id = "task_gap12_v3"` transitions to `VERIFYING` under `worker_gamma`.
   - Caller invokes `kernel.transition(t3_id, "FAILED", lease_id=l3.lease_id, actor="worker_gamma", reason="sabotage_in_verifying_phase")`.
   - *Current Code Result:* Terminates task without independent verifier indictment (`VULNERABILITY_PROVEN_RED`).
   - *Expected Protected Behavior:* Direct transition raises `InvalidTransition` (`status = "PROTECTED_GREEN_InvalidTransition"`).

4. **Vector 4: Stolen Lease Sabotage (lines 197–234):**
   - Task `t4_id = "task_gap12_v4"` claimed and started by `legitimate_worker_delta` with lease `l4.lease_id`.
   - Rogue actor `rogue_saboteur_delta` uses the stolen `lease_id=l4.lease_id` and calls `kernel.transition(t4_id, "FAILED", lease_id=l4.lease_id, actor="rogue_saboteur_delta", reason="malicious_kill_via_stolen_lease")`.
   - *Current Code Result:* `_assert_lease()` checks lease validity in DB, but does NOT check `actor == lease['worker_id']`. The task is killed in `FAILED`, bypassing orphan/crash recovery (`UNKNOWN -> RECOVERING -> RECONCILING`) (`VULNERABILITY_PROVEN_RED`).
   - *Expected Protected Behavior:* Direct transition raises `InvalidTransition` (`status = "PROTECTED_GREEN_InvalidTransition"`).

#### Trigger Condition for `ALL_VECTORS_PROTECTED_GREEN`:
Located in `tools/probes/probe_gap12_delta_audit.py:322–327`:
```python
elif all_green and results.get("sqlite_events_count_failed") == 0 and not results.get("sqlite_tasks_state_any_failed"):
    print(" >> GREEN STATE CONFIRMED: All 4 exploit vectors protected by InvalidTransition.")
    print(" >> Tasks and events verified in database: 0 unauthorized transitions to FAILED.")
    print(" >> Anti-Placebo Falsification Condition Satisfied.")
    print(" >> Verdict: ALL_VECTORS_PROTECTED_GREEN")
    results["overall_verdict"] = "ALL_VECTORS_PROTECTED_GREEN"
```
Exact condition components:
1. `all_green == True`: All 4 vectors must catch `InvalidTransition` and set `val["status"] == "PROTECTED_GREEN_InvalidTransition"`.
2. `sqlite_events_count_failed == 0`: Direct physical query `SELECT COUNT(*) FROM events WHERE to_state='FAILED'` returns 0 rows.
3. `not sqlite_tasks_state_any_failed`: Direct physical query `SELECT state FROM tasks` returns 0 rows where `state == 'FAILED'`.
4. Script returns exit code 0 (`sys.exit(0)`).

---

### 1.2 Existing Test Suite Audit & Caller Impact

An exhaustive AST scan across the entire repository (`tests/`, `scp/`, `tools/`) for all callers of `transition(..., "FAILED")` identified exactly 3 production locations:
1. `scp/ask_kernel_adapter.py:430` (inside `AskKernelAdapter.fail()`)
2. `scp/hands/task_kernel_bridge.py:445` (inside `TaskKernelBridge.execute()`, policy blocked path)
3. `scp/hands/task_kernel_bridge.py:582` (inside `TaskKernelBridge.execute()`, pre-dispatch failure handler)

#### Tests Directly Impacted when Direct Transition to `FAILED` is Blocked:

1. **`tests/T04_kernel/test_adversarial_kernel_flaws.py::test_ask_kernel_adapter_caller_fail_and_finalize_integration` (lines 862–913):**
   - **Current Code:**
     ```python
     # Part 1: adapter.fail() sets task state to FAILED
     task1 = adapter.begin(req.question, list(req.contexts), req.retrieved_context, "session-fail")
     t1_id = task1["task_id"]
     assert adapter.kernel.get_task(t1_id)["state"] == "RUNNING"
     adapter.fail(task1, reason="upstream handler failed")
     assert adapter.kernel.get_task(t1_id)["state"] == "FAILED"
     ```
   - **Failure Mode if Unmigrated:** `adapter.fail()` invokes `self.kernel.transition(task["task_id"], "FAILED", actor="ask-kernel-adapter", reason=reason)`. When `transition()` raises `InvalidTransition`, lines 440–446 catch `Exception as exc`, log non-fatal observation, and silently return. The task in DB remains in `RUNNING`. Line 891 will FAIL with `AssertionError: assert 'RUNNING' == 'FAILED'`.
   - **Migration Requirement:**
     - Update `scp/ask_kernel_adapter.py:426` to call `self.kernel.commit_failed()` using `task["task_id"]`, `task.get("lease_id")`, `actor="ask-route-worker"`, `failure_classification="FATAL"`, and `indictment_ref=f"indictment://ask-adapter/{task['task_id']}"`.
     - The test in `test_adversarial_kernel_flaws.py` will then PASS cleanly without altering test assertions.

2. **`tests/T03_capability/test_hands_authority_pep.py` (9 tests total, 3 tests asserting `taskState == 'FAILED'`):**
   - `test_bridge_rejects_missing_capability_token_fail_closed` (line 185)
   - `test_bridge_rejects_scope_mismatch_fail_closed` (line 230)
   - `test_bridge_rejects_revoked_token_fail_closed` (line 259)
   - **Current Code:**
     ```python
     assert kernel_info.get("taskState") == "FAILED"
     assert db_task["state"] == "FAILED"
     ```
   - **Failure Mode if Unmigrated:** `TaskKernelBridge.execute()` calls `self.kernel.transition(task_id, "FAILED", actor="hands-kernel-bridge", ...)` at line 445 and line 582. Direct transition to `FAILED` raises `InvalidTransition`, leaving task state as `RUNNING`. Assertions on lines 207, 218, 252, 283 will fail.
   - **Migration Requirement:**
     - Update `scp/hands/task_kernel_bridge.py:445` and line 582 to invoke `self.kernel.commit_failed(task_id=task_id, lease_id=lease.lease_id, actor=self.worker_id, failure_classification="FATAL", indictment_ref=f"indictment://hands-bridge/policy_denied/{action}", details={"action": action})`.
     - Ensure `actor` passed matches `self.worker_id` (the lease owner registered in `self.kernel.claim()`).
     - All 9 PEP tests will then PASS with 100% compliance.

---

## 2. Logic Chain

1. **Premise 1 (Anti-Placebo & INV-GAP12-01):**
   `TaskKernel.transition()` currently allows any caller to transition tasks to `FAILED` without a valid lease, actor authentication, error classification, or indictment reference. This was confirmed by `tools/probes/probe_gap12_delta_audit.py` achieving `ALL_VECTORS_PROVEN_RED` (Observation 1.1).

2. **Premise 2 (Guard Symmetry with GAP-11):**
   In GAP-11, `transition()` was hardened with:
   ```python
   if to_state == "COMPLETED":
       raise InvalidTransition("direct transition to COMPLETED is forbidden; use commit_completed() with valid evidence")
   ```
   To satisfy `INV-GAP12-01`, `transition()` must enforce the exact structural twin:
   ```python
   if to_state in ("COMPLETED", "FAILED"):
       raise InvalidTransition(f"direct transition to {to_state} is forbidden; use commit_{to_state.lower()}() with valid evidence")
   ```
   This immediately forces all failure transitions to route through `commit_failed()`.

3. **Premise 3 (Triggering `ALL_VECTORS_PROTECTED_GREEN`):**
   Because the probe explicitly calls `kernel.transition(..., "FAILED")` across all 4 vectors, adding the guard to `transition()` ensures all 4 calls catch `InvalidTransition`, record `PROTECTED_GREEN_InvalidTransition`, and leave 0 rows in `tasks` and `events` with `state='FAILED'`. This satisfies lines 322–327 of `probe_gap12_delta_audit.py` to produce `ALL_VECTORS_PROTECTED_GREEN` (Observation 1.1).

4. **Premise 4 (Downstream Migration Mandate):**
   Because `AskKernelAdapter.fail()` and `TaskKernelBridge.execute()` directly call `transition(..., "FAILED")` (Observation 1.2), migrating `TaskKernel` without updating these callers would cause `test_ask_kernel_adapter_caller_fail_and_finalize_integration` and `test_hands_authority_pep.py` to break. Therefore, downstream migration to `commit_failed()` is mandatory for zero-regression compliance.

5. **Premise 5 (Leaseholder Ownership Binding):**
   In `TaskKernelBridge`, `self.kernel.claim(task_id, self.worker_id)` assigns the lease to `self.worker_id`. Therefore, `commit_failed()` must assert that `caller_actor == lease['worker_id']`. If an adversary passes a stolen `lease_id` with a mismatched actor, it must raise `InvalidTransition` (Observation 1.1 Vector 4).

6. **Premise 6 (Retry Budget & Recovery Routing):**
   In `tasks` table, `max_attempts` is stored at task creation. In `leases` table, each claim records an attempt. By checking `attempts < task['max_attempts']` when `failure_classification == "RETRYABLE"`, `commit_failed()` can route transient failures to `UNKNOWN` (or `RETRY_SCHEDULED`), incrementing attempt state and releasing the lease without prematurely killing the task. If exhausted or `failure_classification == "FATAL"`, it transitions to terminal `FAILED`.

---

## 3. Caveats

1. **Single-Process SQLite Scope:**
   The current testing environment uses SQLite WAL mode on local disk. Distributed multi-node consensus (e.g., PostgreSQL/Raft) is outside current scope and was not evaluated.
2. **Schema Non-Mutation:**
   No DDL changes (`ALTER TABLE`) are performed. `max_attempts` already exists in `tasks`; `attempts` is computed from `leases` history or stored in event payloads; failure details and `indictment_ref` are stored in existing `events.payload_json` and `tasks.updated_at`.
3. **GAP-13 Scope Boundary:**
   GAP-13 (`WAITING_APPROVAL -> READY` bypass) is documented in `EMERGENCY_GAP_REPORT.md` but is strictly out-of-scope for GAP-12 remediation. No changes to `WAITING_APPROVAL` are proposed.

---

## 4. Conclusion & Complete Design

### 4.1 Whole-System Mermaid Causal Graph (FA-12 Step 1)

```mermaid
graph TD
    %% Entrypoints
    subgraph Triggers["Triggers & Entrypoints"]
        E1["Direct transition(task_id, 'FAILED')"]
        E2["commit_failed(task_id, lease_id, actor, classification, indictment_ref, details)"]
        E3["AskKernelAdapter.fail(task, reason)"]
        E4["TaskKernelBridge.execute() policy/runtime failure"]
    end

    %% Routing
    E3 -->|Routes to| E2
    E4 -->|Routes to| E2

    %% Branch 1: Direct Guard
    subgraph Guard["Transition Guard (INV-GAP12-01)"]
        B1{"to_state == 'FAILED'?"}
        E1 --> B1
        B1 -->|Yes| R1["Branch 1: Raise InvalidTransition<br/>('direct transition to FAILED is forbidden')"]
    end

    %% commit_failed Execution Pipeline
    subgraph CommitFailed["commit_failed() Pipeline"]
        %% Validation checks
        C_Exist{"Task exists in DB?"}
        E2 --> C_Exist
        C_Exist -->|No| R2a["Branch 2a: Raise NotFound / KernelError"]
        C_Exist -->|Yes| C_Lease{"Lease valid, unexpired,<br/>unreleased & active?"}
        
        C_Lease -->|No| R2b["Branch 2b: Raise StaleLease / OptimisticLockError"]
        C_Lease -->|Yes| C_State{"Task state in active leased states<br/>(RUNNING, WAITING_TOOL, VERIFYING)?"}
        
        C_State -->|Terminal or Unleased| R2c["Branch 2c: Raise InvalidTransition<br/>('terminal task is immutable')"]
        C_State -->|Valid| C_Actor{"actor == lease.worker_id?"}
        
        C_Actor -->|No: Stolen Lease| R3["Branch 3: Raise InvalidTransition<br/>('actor does not own active lease')"]
        C_Actor -->|Yes| C_Indict{"indictment_ref non-empty?"}
        
        C_Indict -->|No / Empty| R4["Branch 4: Raise KernelError<br/>('failure requires indictment_ref')"]
        C_Indict -->|Yes| C_Classify{"Classification & Attempts Check"}

        %% Branch 5, 6, 7
        C_Classify -->|RETRYABLE & attempts < max_attempts| B5["Branch 5: Move to UNKNOWN / RETRY_SCHEDULED<br/>Release lease; Decrement active queue<br/>Log TASK_RETRY_SCHEDULED event"]
        C_Classify -->|RETRYABLE & attempts >= max_attempts| B6["Branch 6: Move to terminal FAILED<br/>Release lease; Decrement active queue<br/>Log TASK_FAILED (exhausted=True) event"]
        C_Classify -->|FATAL (regardless of attempts)| B7["Branch 7: Move to terminal FAILED<br/>Release lease; Decrement active queue<br/>Log TASK_FAILED (fatal=True) event"]
    end

    %% Downstream Integrations
    subgraph Integrations["Downstream Verification"]
        B8["Branch 8: AskKernelAdapter.fail() -> Verified terminal FAILED"]
        B9["Branch 9: TaskKernelBridge.execute() -> Verified terminal FAILED"]
        B7 --> B8
        B7 --> B9
    end

    classDef danger fill:#542426,stroke:#e5534b,color:#e6edf3;
    classDef safe fill:#1b4428,stroke:#57ab5a,color:#e6edf3;
    classDef decision fill:#23272e,stroke:#d29922,color:#e6edf3;
    classDef neutral fill:#1f242c,stroke:#4b5263,color:#abb2bf;

    class R1,R2a,R2b,R2c,R3,R4 danger;
    class B5,B6,B7,B8,B9 safe;
    class B1,C_Exist,C_Lease,C_State,C_Actor,C_Indict,C_Classify decision;
    class E1,E2,E3,E4 neutral;
```

---

### 4.2 FA-13 Coverage Matrix (All 9 Causal Branches)

| Branch ID | Causal Branch Description | Trigger & Input Conditions | Target Function & Line Range | Expected Result & Database Mutation | Concrete Test Function / Location | Status |
|---|---|---|---|---|---|---|
| **BRANCH-01** | Direct `transition(..., "FAILED")` blocked | External caller invokes `transition(task_id, "FAILED")` from ANY state (non-existent, CREATED, PLANNING, READY, QUEUED, LEASED, RUNNING, WAITING_TOOL, VERIFYING, CHECKPOINTED, UNKNOWN, RECOVERING, RECONCILING, HUMAN_REVIEW, RETRY_SCHEDULED) | `scp/task_kernel_parts/taskkernel.py:253` | Raises `InvalidTransition("direct transition to FAILED is forbidden; use commit_failed() with valid failure evidence")`. Zero DB rows changed. | `test_adversarial_kernel_flaws.py::test_direct_transition_to_failed_forbidden_from_all_states` | **COVERED (Spec Ready)** |
| **BRANCH-02** | `commit_failed()` with invalid lease or nonexistent task | Caller invokes `commit_failed()` with invalid/expired lease, released lease, or non-existent `task_id`, or on terminal task | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Raises `NotFound`, `StaleLease`, or `InvalidTransition`. Zero state mutation. | `test_adversarial_kernel_flaws.py::test_commit_failed_invalid_lease_or_nonexistent_task` | **COVERED (Spec Ready)** |
| **BRANCH-03** | `commit_failed()` actor mismatch (Stolen Lease) | Rogue caller calls `commit_failed()` quoting valid `lease_id` where `actor != lease['worker_id']` | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Raises `InvalidTransition(f"actor {actor} does not own active lease {lease_id}")`. Lease remains active. | `test_adversarial_kernel_flaws.py::test_commit_failed_stolen_lease_actor_mismatch_prevented` | **COVERED (Spec Ready)** |
| **BRANCH-04** | `commit_failed()` missing or empty `indictment_ref` | Caller calls `commit_failed()` with `indictment_ref=""`, `None`, or whitespace | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Raises `KernelError("failure commitment requires valid indictment_ref and error details")`. Fail-closed. | `test_adversarial_kernel_flaws.py::test_commit_failed_missing_or_empty_indictment_rejected` | **COVERED (Spec Ready)** |
| **BRANCH-05** | `commit_failed()` retryable error with attempts < max_attempts | Task with `max_attempts=3` fails attempt 1 with `classification="RETRYABLE"` | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Moves task state to `UNKNOWN` (or `RETRY_SCHEDULED`). Releases lease. Decrements queue active. Records `TASK_RETRY_SCHEDULED` event. NOT FAILED. | `test_adversarial_kernel_flaws.py::test_commit_failed_retryable_routes_to_unknown_and_preserves_budget` | **COVERED (Spec Ready)** |
| **BRANCH-06** | `commit_failed()` retry budget exhausted | Task with `max_attempts=2` fails attempt 2 with `classification="RETRYABLE"` | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Moves task state to terminal `FAILED`. Releases lease. Records `TASK_FAILED` with `exhausted: True`. Task immutable. | `test_adversarial_kernel_flaws.py::test_commit_failed_retry_budget_exhausted_moves_to_terminal_failed` | **COVERED (Spec Ready)** |
| **BRANCH-07** | `commit_failed()` fatal error classification | Task with `max_attempts=5` encounters unrecoverable error on attempt 1 with `classification="FATAL"` | `scp/task_kernel_parts/taskkernel.py::commit_failed` | Immediately transitions to terminal `FAILED`. Releases lease. Records `TASK_FAILED` with `fatal: True`. | `test_adversarial_kernel_flaws.py::test_commit_failed_fatal_classification_terminates_immediately` | **COVERED (Spec Ready)** |
| **BRANCH-08** | Downstream `AskKernelAdapter.fail()` integration | Upstream handler fails during RAG answer flow; adapter calls `fail()` | `scp/ask_kernel_adapter.py:426` -> `commit_failed()` | Task transitions to `FAILED` in SQLite with `TASK_FAILED` event; trace journal records `outcome="FAILED"`. | `test_adversarial_kernel_flaws.py::test_ask_kernel_adapter_caller_fail_and_finalize_integration` | **COVERED (Spec Ready)** |
| **BRANCH-09** | Downstream `TaskKernelBridge` error handling integration | Capability token missing, scope mismatched, or token revoked during tool dispatch | `scp/hands/task_kernel_bridge.py:445, 582` -> `commit_failed()` | Task transitions to `FAILED`, lease marked released, `taskState="FAILED"`, zero disk side-effects. | `tests/T03_capability/test_hands_authority_pep.py` (all 9 tests) | **COVERED (Spec Ready)** |

---

### 4.3 Specifications for Implementation & Concrete Test Code

The implementer (`worker_1` / `worker_2`) should implement the following concrete artifacts:

#### 1. `TaskKernel.commit_failed()` Signature & Contract:
```python
def commit_failed(
    self,
    task_id: str,
    lease_id: str,
    actor: str,
    failure_classification: str,
    indictment_ref: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit task failure or route to retry/recovery under authenticated lease authority.
    
    Invariants Enforced:
    - INV-GAP12-01: Terminal FAILED requires commit_failed().
    - INV-GAP12-02: Non-empty indictment_ref mandatory.
    - INV-GAP12-03: Retry budget preserved (RETRYABLE & attempts < max_attempts -> UNKNOWN).
    - INV-GAP12-04: Strict lease validation and actor ownership.
    """
    if not indictment_ref or not str(indictment_ref).strip():
        raise KernelError("failure commitment requires valid indictment_ref and error details")
    
    self._begin()
    try:
        lease = self._assert_lease(lease_id, task_id)
        if actor and lease["worker_id"] != actor:
            raise InvalidTransition(f"actor {actor} does not own active lease {lease_id}")
            
        task = self._task(task_id)
        if task["state"] in TERMINAL:
            raise InvalidTransition("terminal task is immutable")
        if task["state"] not in {"RUNNING", "WAITING_TOOL", "VERIFYING", "LEASED"}:
            raise InvalidTransition(f"cannot commit failure from state {task['state']}")
        if task["active_lease_id"] != lease_id:
            raise StaleLease(f"failure lease {lease_id} does not match active task lease {task['active_lease_id']}")
            
        is_system = getattr(self, "_system_authority", False)
        bound = getattr(self, "_bound_leases", {}).get(task_id)
        if not is_system:
            if not bound:
                raise StaleLease(f"kernel instance does not possess active lease authority for task {task_id}")
            if bound != lease_id:
                raise StaleLease(f"caller lease {lease_id} does not match bound instance lease {bound}")
                
        # Count total attempts for this task
        attempts_row = self.conn.execute(
            "SELECT COUNT(DISTINCT attempt_id) AS n FROM leases WHERE task_id=?", (task_id,)
        ).fetchone()
        attempts = int(attempts_row["n"]) if attempts_row else 1
        max_attempts = int(task["max_attempts"])
        
        is_retryable = (failure_classification.upper() == "RETRYABLE") and (attempts < max_attempts)
        target_state = "UNKNOWN" if is_retryable else "FAILED"
        event_type = "TASK_RETRY_SCHEDULED" if is_retryable else "TASK_FAILED"
        
        old_state = task["state"]
        cur = self.conn.execute(
            "UPDATE tasks SET state=?,version=version+1,active_lease_id=NULL,active_fencing_token=0,updated_at=? WHERE task_id=? AND version=?",
            (target_state, now_iso(), task_id, task["version"]),
        )
        if cur.rowcount != 1:
            raise StaleLease(f"concurrency conflict committing failure on task {task_id}")
            
        payload = {
            "indictment_ref": indictment_ref,
            "failure_classification": failure_classification,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "lease_id": lease_id,
            "details": details or {},
        }
        self._append_event(task_id, event_type, old_state, target_state, actor, f"failure_{failure_classification.lower()}", payload)
        
        self.conn.execute("UPDATE leases SET released=1,version=version+1 WHERE lease_id=? AND released=0", (lease_id,))
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

---

## 5. Verification Method

To independently verify all findings and confirm remediation:

1. **Anti-Placebo Probe Verification:**
   ```powershell
   python tools/probes/probe_gap12_delta_audit.py
   ```
   *Expected Output after remediation:*
   - All 4 vectors return `Verdict: PROTECTED_GREEN_InvalidTransition`.
   - `sqlite_events_count_failed`: 0.
   - `sqlite_tasks_state_any_failed`: False.
   - Final line: `Verdict: ALL_VECTORS_PROTECTED_GREEN`.
   - Exit code: 0.

2. **Kernel Test Suite Regression & Causal Branch Verification:**
   ```powershell
   pytest tests/T04_kernel/ -v
   ```
   *Expected Output:*
   - All 78+ existing tests pass 100%.
   - New tests covering Branches 1 through 7 pass 100%.
   - `test_ask_kernel_adapter_caller_fail_and_finalize_integration` passes 100%.
   - Exit code: 0.

3. **Capability PEP Suite Verification:**
   ```powershell
   pytest tests/T03_capability/test_hands_authority_pep.py -v
   ```
   *Expected Output:*
   - All 9 tests pass 100%.
   - Exit code: 0.

4. **T00 Meta-Audit Compliance:**
   ```powershell
   python tools/t00_meta_audit.py
   ```
   *Expected Output:*
   - `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`
   - Exit code: 0.

5. **FA-12 Step 4 Hardware/Physical Database Inspection:**
   ```powershell
   python -c "
   import sqlite3
   # Inspect temporary or live sqlite file
   conn = sqlite3.connect('tools/probes/test_db.sqlite3')
   print(conn.execute('SELECT task_id, state, active_lease_id FROM tasks').fetchall())
   print(conn.execute('SELECT event_id, type, from_state, to_state, actor FROM events').fetchall())
   "
   ```
   *Invalidation Conditions:*
   - Any raw transition to `FAILED` succeeds without raising `InvalidTransition`.
   - Any task moves to terminal `FAILED` without an associated non-empty `indictment_ref` in `events`.
   - A task with `attempts < max_attempts` and retryable classification is terminated into `FAILED`.
   - A stolen lease holder succeeds in committing task failure.
