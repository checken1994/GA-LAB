# SCP Task Kernel State Machine & Runtime Causal Chain Investigation Report

## 1. Observation

### 1.1 Source Locations & Commit Identity
- **Repository Path**: `c:\Users\check\Downloads\scp`
- **Git Branch**: `experts-4.0.3-434green`
- **Exact HEAD SHA**: `48e5ca8dd0867d1257103ea66f73be752d785b60`
- **Primary Implementation Files**:
  - `scp/task_kernel.py` (facade, context-bound lease wrappers, constants)
  - `scp/task_kernel_parts/taskkernel.py` (core class `TaskKernel`, SQL schema, storage operations)
  - `scp/kernel_storage.py` (storage engine, per-thread SQLite connections, transaction handling)
  - `scp/hands/task_kernel_bridge.py` (Hands executor lifecycle wrapper)
  - `scp/ask_kernel_adapter.py` (RAG / Ask route lifecycle wrapper)
- **Specification & Mandate References**:
  - `.agents/AGENTS.md` (line 18): `| **scp-task-kernel-review** | Kiểm tra tính bất biến của State Machine trong Task Kernel (15 trạng thái hợp lệ, khóa chuyển đổi nguyên tử). |`
  - `.agents/GEMINI.md` (line 18): verbatim identical to AGENTS.md.
  - `.agents/skills/scp-task-kernel-review/SKILL.md` (lines 43-52, section State machine toi thieu):
    - `CREATED -> PLANNING -> READY -> QUEUED -> LEASED -> RUNNING`
    - `RUNNING -> WAITING_TOOL -> VERIFYING -> COMPLETED`
    - `RUNNING/WAITING_TOOL -> RECOVERING/UNKNOWN/HUMAN_REVIEW/FAILED/CANCELLED`
    - `RECOVERING -> CHECKPOINTED/QUEUED/HUMAN_REVIEW/FAILED`
  - `tests/T09_golden_task/test_e2e_scp_complete.py` (line 15): `"- Tạo một chuỗi Task tuân thủ 15 trạng thái bất biến."`
  - `audit_and_optimization_plan.md` (lines 33-36): `"The STATES set actually defines 17 states..."`

### 1.2 State Machine Definition in Code (`scp/task_kernel.py`)
In `scp/task_kernel.py` (lines 17-43):
```python
STATES = {
    "CREATED", "PLANNING", "READY", "QUEUED", "LEASED", "RUNNING",
    "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN", "RECOVERING",
    "RECONCILING", "HUMAN_REVIEW", "RETRY_SCHEDULED", "COMPLETED",
    "FAILED", "CANCELLED",
}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
ALLOWED_TRANSITIONS = {
    "CREATED": {"PLANNING", "CANCELLED"},
    "PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"},
    "WAITING_APPROVAL": {"READY", "CANCELLED"},
    "READY": {"QUEUED", "CANCELLED"},
    "QUEUED": {"LEASED", "CANCELLED"},
    "LEASED": {"RUNNING", "RECOVERING", "CANCELLED"},
    "RUNNING": {"WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "RECOVERING", "HUMAN_REVIEW", "FAILED", "CANCELLED"},
    "WAITING_TOOL": {"VERIFYING", "UNKNOWN", "RECOVERING", "FAILED", "CANCELLED"},
    "VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"},
    "CHECKPOINTED": {"RUNNING", "QUEUED", "CANCELLED"},
    "UNKNOWN": {"RECONCILING", "HUMAN_REVIEW", "RECOVERING", "FAILED", "CANCELLED"},
    "HUMAN_REVIEW": {"READY", "CANCELLED", "FAILED"},
    "RECOVERING": {"RECONCILING", "CHECKPOINTED", "QUEUED", "HUMAN_REVIEW", "FAILED"},
    "RECONCILING": {"RECOVERING", "CHECKPOINTED", "QUEUED", "HUMAN_REVIEW", "FAILED", "CANCELLED"},
    "RETRY_SCHEDULED": {"QUEUED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}
```

In `scp/task_kernel.py` (lines 234-235):
```python
    if to_state not in STATES and to_state != "WAITING_APPROVAL":
        raise InvalidTransition(f"unknown target state {to_state}")
```
And in `scp/task_kernel_parts/taskkernel.py` (lines 115-116):
```python
        if to_state not in STATES and to_state != 'WAITING_APPROVAL':
            raise InvalidTransition(f'unknown target state {to_state}')
```

### 1.3 State Counts
1. **Mandate states (15)**:
   `CREATED`, `PLANNING`, `READY`, `QUEUED`, `LEASED`, `RUNNING`, `WAITING_TOOL`, `VERIFYING`, `CHECKPOINTED`, `UNKNOWN`, `RECOVERING`, `HUMAN_REVIEW`, `COMPLETED`, `FAILED`, `CANCELLED`.
2. **`STATES` constant (17)**:
   The 15 mandate states plus `RECONCILING` and `RETRY_SCHEDULED`.
3. **Active runtime states in transition map & guards (18)**:
   The 17 states in `STATES` plus `WAITING_APPROVAL`.

### 1.4 Database Schema & Concurrency Primitives (`scp/task_kernel_parts/taskkernel.py:49-67`)
- Tables:
  - `control`: `id INTEGER PRIMARY KEY CHECK (id=1), global_kill INTEGER, global_kill_epoch INTEGER`
  - `tasks`: `task_id PRIMARY KEY, owner, goal, risk_tier, deadline_ms, max_attempts, input_hash, priority, state, version, created_at, updated_at`
  - `events`: `event_id PRIMARY KEY, task_id, seq, type, from_state, to_state, actor, reason, payload_json, policy_hash, prev_event_hash, event_hash, created_at, UNIQUE(task_id, seq)`
  - `leases`: `lease_id PRIMARY KEY, task_id, attempt_id, worker_id, issued_at, expires_at, heartbeat_at, fencing_token, global_kill_epoch, released`
  - `checkpoints`: `checkpoint_id PRIMARY KEY, task_id, attempt_id, step_id, state, planned_action_hash, capability_epoch, idempotency_key, pre_observation_ref, post_observation_ref, tool_result_json, verifier_verdict, payload_hash, created_at`
  - `idempotency`: `logical_key PRIMARY KEY, task_id, step_id, action_type, resource_identity, status, result_ref, created_at`
  - `queue_accounts`: `owner PRIMARY KEY, active, dispatch_count, last_dispatch_at`
- Storage Layer:
  - `make_storage(db_path)` in `scp/kernel_storage.py` configures SQLite in WAL mode with per-thread connections (`threading.local()`) and busy timeout (5000ms).
  - `_begin()` executes `BEGIN IMMEDIATE` via `storage.begin()` with bounded lock-retry to prevent `database is locked` multi-threaded write contention.

### 1.5 Execution-Context Lease Fencing (`scp/task_kernel.py:158-293`)
- `_LEASE_CONTEXT`: `ContextVar[dict[tuple[int, str], str]]` maps `(id(kernel), task_id)` to `lease_id`.
- `_transition_fenced_by_bound_lease`: Revalidates lease inside the state-write transaction:
  ```python
  lease_id = _bound_lease_id(self, task_id)
  if not lease_id:
      return _original_transition(...)
  self._begin()
  try:
      self._assert_lease(lease_id, task_id)
      # transition logic ...
  ```
- Monotonic fencing token:
  `latest = SELECT COALESCE(MAX(fencing_token), 0) FROM leases WHERE task_id=?`
  `if int(lease['fencing_token']) != int(latest): raise StaleLease(lease_id)`

### 1.6 Verbatim Runtime Verification Execution Outputs
1. **Kernel Test Suite (`pytest tests/T04_kernel/ -v`)**:
```text
tests/T04_kernel/test_ask_kernel_adapter_verify.py::test_rag_ask_with_passing_judge_is_verified PASSED [  4%]
tests/T04_kernel/test_ask_kernel_adapter_verify.py::test_chat_ask_without_contexts_uses_judge_semantics PASSED [  9%]
tests/T04_kernel/test_ask_kernel_adapter_verify.py::test_failing_judge_contradicts_any_ask PASSED [ 13%]
tests/T04_kernel/test_ask_kernel_terminal_race.py::test_cancelled_task_before_finalize_withholds_unverified_response PASSED [ 18%]
tests/T04_kernel/test_ask_kernel_terminal_race.py::test_cancel_between_precheck_and_verifying_transition_fails_closed PASSED [ 22%]
tests/T04_kernel/test_kernel_crash_consistency.py::test_crash_between_event_and_projection_is_repaired_by_rebuild PASSED [ 27%]
tests/T04_kernel/test_kernel_crash_consistency.py::test_tampered_journal_is_fail_closed PASSED [ 31%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_duplicate_request_returns_replayed_response PASSED [ 36%]
tests/T04_kernel/test_orphan_sweep_keeps_fresh_lease_and_reconciles_stale_one PASSED [ 40%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_event_does_not_poison_rebuild_projection PASSED [ 45%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_checkpoint_still_rejects_invalid_state PASSED [ 50%]
tests/T04_kernel/test_kernel_p1_regressions.py::test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch PASSED [ 54%]
tests/T04_kernel/test_kernel_storage.py::test_task_kernel_uses_injected_storage_for_transaction_lifecycle PASSED [ 59%]
tests/T04_kernel/test_kernel_storage.py::test_task_kernel_backup_is_delegated_to_storage PASSED [ 63%]
tests/T04_kernel/test_lease_fencing_idempotency.py::test_stale_lease_cannot_create_idempotency_claim PASSED [ 68%]
tests/T04_kernel/test_lease_fencing_idempotency.py::test_stale_lease_cannot_complete_existing_idempotency_claim PASSED [ 72%]
tests/T04_kernel/test_lease_fencing_idempotency.py::test_fresh_recovery_reader_can_probe_duplicate_without_mutating_it PASSED [ 77%]
tests/T04_kernel/test_task_kernel_mutation_contract.py::test_task_contract_rejects_boundary_values PASSED [ 81%]
tests/T04_kernel/test_task_kernel_mutation_contract.py::test_transition_contract_and_happy_lifecycle PASSED [ 86%]
tests/T04_kernel/test_task_kernel_mutation_contract.py::test_human_review_remains_nonterminal_and_counted_as_in_flight PASSED [ 90%]
tests/T04_kernel/test_transition_lease_fencing.py::test_expired_unswept_lease_cannot_transition_task_or_journal PASSED [ 95%]
tests/T04_kernel/test_transition_lease_fencing.py::test_boot_recovery_temporarily_supersedes_but_does_not_erase_stale_fence PASSED [100%]
============================= 22 passed in 4.20s ==============================
```

2. **Recovery & Chaos Test Suite (`pytest tests/T10_recovery/ -v`)**:
```text
tests/T10_recovery/test_adversarial_chaos_matrix.py::test_chaos_hard_kill_after_checkpoint_recovers_to_recovering PASSED [ 11%]
tests/T10_recovery/test_adversarial_chaos_matrix.py::test_chaos_hard_kill_in_running_goes_to_human_review PASSED [ 22%]
tests/T10_recovery/test_kernel_chaos_recovery.py::test_hard_kill_then_boot_recovery_replays_journal PASSED [ 33%]
tests/T10_recovery/test_kernel_chaos_recovery.py::test_recover_on_boot_never_tamperes_corrupted_journal PASSED [ 44%]
tests/T10_recovery/test_reconciliation_outcome_contract.py::test_ambiguous_reconciliation_outcomes_are_durable_and_never_retryable[PARTIAL-RECONCILED_PARTIAL-RECONCILE_PARTIAL] PASSED [ 55%]
tests/T10_recovery/test_reconciliation_outcome_contract.py::test_ambiguous_reconciliation_outcomes_are_durable_and_never_retryable[CONFLICT-RECONCILED_CONFLICT-RECONCILE_CONFLICT] PASSED [ 66%]
tests/T10_recovery/test_reconciliation_outcome_contract.py::test_ambiguous_reconciliation_requires_independent_verifier[PARTIAL] PASSED [ 77%]
tests/T10_recovery/test_reconciliation_outcome_contract.py::test_ambiguous_reconciliation_requires_independent_verifier[CONFLICT] PASSED [ 88%]
tests/T10_recovery/test_reconciliation_outcome_contract.py::test_lowercase_partial_is_normalized_without_becoming_retryable PASSED [100%]
============================== 9 passed in 1.22s ==============================
```

3. **Meta-Audit Pre-Commit Check (`python tools/t00_meta_audit.py`)**:
```text
=== T00 META AUDIT ===
FA-01 check: PASS
FA-02 check: PASS
FA-03 check: PASS
FA-04 check: PASS
FA-05 check: PASS
FA-06 check: PASS
FA-07 check: PASS
ALL CHECKS PASSED
```

4. **Skill Contract Verification (`python tools/verify_scp_test_skill_contract.py`)**:
```json
{
  "commit": "48e5ca8dd0867d1257103ea66f73be752d785b60",
  "dna_principle_count": 29,
  "errors": [],
  "observed_gate_count": 14,
  "status": "PASS_WITHIN_SCOPE"
}
```

---

## 2. Logic Chain

### 2.1 Discrepancy Resolution: 15-State Mandate vs 18 Active Runtime States
1. **Mandate Origin (Observation 1.1)**:
   `AGENTS.md`, `GEMINI.md`, and `test_e2e_scp_complete.py` mandate:
   `Kiểm tra tính bất biến của State Machine trong Task Kernel (15 trạng thái hợp lệ, khóa chuyển đổi nguyên tử)`.
   In `scp-task-kernel-review/SKILL.md` (§ State machine tối thiểu), exactly 15 states are listed:
   `CREATED, PLANNING, READY, QUEUED, LEASED, RUNNING, WAITING_TOOL, VERIFYING, CHECKPOINTED, UNKNOWN, RECOVERING, HUMAN_REVIEW, COMPLETED, FAILED, CANCELLED`.

2. **Runtime Implementation (Observation 1.2 & 1.3)**:
   In `scp/task_kernel.py`:
   - `STATES` set contains 17 states (the 15 mandate states plus `RECONCILING` and `RETRY_SCHEDULED`).
   - `ALLOWED_TRANSITIONS` contains 18 keys (adds `WAITING_APPROVAL`).
   - Transition validation in both `task_kernel.py:234` and `taskkernel.py:115` explicitly executes:
     `if to_state not in STATES and to_state != 'WAITING_APPROVAL': raise InvalidTransition(...)`
   Therefore, the active state space in live runtime execution consists of exactly 18 states.

3. **Analysis of the 3 Divergent States**:

   - **State 1: `RECONCILING`**
     - **Definition**: Defined in `scp/task_kernel.py:20, 38` and implemented in `scp/task_kernel_parts/taskkernel.py:382-440`.
     - **Purpose & Rationale**: Implements SCP DNA #2 (*Fail-Closed by Default*) and DNA #26 (*Reality > Model*). When a task executes an external mutating action (such as PC control, file writes, API requests), a crash or network drop after dispatch leaves the external state uncertain (`UNKNOWN`). The system strictly forbids blind retry (`safe_to_retry=False`). The task must transition into `RECONCILING` so an independent verifier reads external post-state evidence (`provider_request_status`, file check). Only if proven `NOT_APPLIED` does it re-enter `QUEUED`; if `APPLIED`, `PARTIAL`, or `CONFLICT`, it escalates to `HUMAN_REVIEW`.
     - **Transitions**:
       - *Incoming*: `UNKNOWN -> RECONCILING`, `RECOVERING -> RECONCILING` (invoked via `enter_reconciling` or `auto_reconcile_orphans`).
       - *Outgoing*: `RECONCILING -> {RECOVERING, CHECKPOINTED, QUEUED, HUMAN_REVIEW, FAILED, CANCELLED}`.
     - **Why it diverged**: The original 15-state specification merged recovery and reconciliation under `RECOVERING` / `UNKNOWN`. Hardening during Phase 4-6 required a distinct durable state for active evidence gathering so that intermediate reconciliation steps are traceable in the event journal without prematurely claiming retryability.

   - **State 2: `RETRY_SCHEDULED`**
     - **Definition**: Defined in `scp/task_kernel.py:20, 39` and referenced in `scp/ask_kernel_adapter.py:85`.
     - **Purpose & Rationale**: Architecturally designed to support backoff-delayed retries for transient failures (e.g. `PROVIDER_TIMEOUT`, `TRANSIENT_NETWORK`) before re-entering `QUEUED`.
     - **Transitions & Critical Defect**:
       - *Outgoing*: `RETRY_SCHEDULED -> {QUEUED, FAILED, CANCELLED}`.
       - *Incoming*: **NONE**. In `ALLOWED_TRANSITIONS`, `RETRY_SCHEDULED` appears as a target in zero states (`set()`). In `TaskKernel.recovery_decision`, transient retries route directly to `QUEUED` (`next_state='QUEUED'`).
     - **Assessment**: `RETRY_SCHEDULED` is an unreachable, orphaned state in the runtime transition graph. It exists in the `STATES` constant and transition map keys, but cannot be transitioned into legally.

   - **State 3: `WAITING_APPROVAL`**
     - **Definition**: Defined in `ALLOWED_TRANSITIONS["PLANNING"]` (`scp/task_kernel.py:26`) and `ALLOWED_TRANSITIONS["WAITING_APPROVAL"]` (`:27`), and heavily used across governance modules (`scp/hands/planner.py`, `scp/governance/external_authority.py`, `scp/policy/retry_policy.py`).
     - **Purpose & Rationale**: High-consequence governance barrier (DNA #4, #11, CE-S01-04). For actions with risk tier R2/R3, external actions, or destructive operations, an action proposal cannot become `READY` without authorization.
     - **Transitions**:
       - *Incoming*: `PLANNING -> WAITING_APPROVAL`.
       - *Outgoing*: `WAITING_APPROVAL -> {READY, CANCELLED}`.
     - **Architectural Anomaly**: `WAITING_APPROVAL` is missing from the `STATES` set in `task_kernel.py:17-22`. To make transitions work, the implementation introduced a special-case exception: `if to_state not in STATES and to_state != 'WAITING_APPROVAL':`. This is a clear leaky abstraction and architectural inconsistency between `STATES` and `ALLOWED_TRANSITIONS`.

---

### 2.2 End-to-End Causal Chains Trace

#### Causal Chain A: Hands Mutating Action (Computer-Use / PC Control Execution)
```text
[Trigger / External Input]
  User or orchestrator calls TaskKernelHandsBridge.execute(action, params, capability_level, approved, request_key)
       |
       v
[Routing / Dispatch]
  Bridge checks definition: definition.mutates_state == True (and dry_run == False)
  Deterministic task_id derived: sha256(request_key)[:32]
  Input hash computed: stable_hash({action, params_hash})
       |
       +--> [Deduplication Branch]: Task already exists in DB
       |      `--> Replay detection: returns {replayed: True, success: False, safeToRetry: False}
       |            (Prevents duplicate external side effect)
       v
[TaskKernel State Transitions - Preparation Phase]
  1. kernel.create_task(task_id, "hands-route", ...)  --> State: CREATED (Event: TASK_CREATED)
  2. kernel.transition(..., "PLANNING")                --> State: PLANNING
  3. [If High-Consequence]:                             --> State: WAITING_APPROVAL
  4. kernel.transition(..., "READY")                   --> State: READY
  5. kernel.transition(..., "QUEUED")                  --> State: QUEUED
       |
       v
[Lease Acquisition & Execution Lock]
  6. kernel.claim(task_id, worker_id, ttl_seconds=60)  --> State: LEASED (Event: LEASE_GRANTED)
     - Atomically sets fencing_token = MAX(fencing_token) + 1
     - Binds lease_id in _LEASE_CONTEXT
  7. kernel.start(task_id, lease_id)                   --> State: RUNNING (Event: WORKER_STARTED)
  8. kernel.idempotency_claim(task_id, action, ...)    --> Idempotency row: CLAIMED
  9. kernel.checkpoint(..., "WAITING_TOOL", ...)       --> Checkpoint persisted with pre_observation_ref
     - Passes secret sanitization (_assert_checkpoint_safe)
     - to_state in checkpoint event remains NULL to prevent projection poisoning
       |
       v
[Subsystem Side Effects (PC Controller / OS Driver Execution)]
  10. Background lease renewal: _heartbeat_until_finished extends lease TTL during awaited execution
  11. await executor.execute(action, params) executes actual driver action (file write, mouse/keyboard)
       |
       +-------------------------------+-------------------------------+
       v                               v                               v
[Branch 1: Policy Blocked]      [Branch 2: Verified Success]    [Branch 3: Ambiguous / Crash]
- Policy denied before side      - Execution succeeds and        - Driver throws exception or
  effect dispatch                 verifier passes                 returns unverified result
- State -> FAILED                - State -> VERIFYING            - record_action_dispatched()
- Lease released                 - Idempotency status:           - State -> UNKNOWN
- Event: STATE_TRANSITION          COMPLETED (evidence_ref)      - safe_to_retry = False
- Result: safeToRetry=False      - commit_verification_result    - Watchdog auto_reconcile_orphans
                                 - State -> COMPLETED              moves UNKNOWN -> RECONCILING
                                 - Lease released                - reconcile_unknown() gathers
                                 - Final Event: TASK_COMPLETED     read-only external evidence:
                                                                   * NOT_APPLIED -> QUEUED (retry)
                                                                   * APPLIED/UNKNOWN -> HUMAN_REVIEW
```

#### Causal Chain B: RAG / Ask Route (`AskKernelAdapter`)
```text
[Trigger / External Input]
  POST /ask HTTP request received with question, contexts, retrieved_context, session_id
       |
       v
[Routing / Admission Control]
  AskKernelAdapter.begin(...) computes deterministic task_id & input_hash
  Backpressure Check: in_flight_count() >= SCP_ASK_MAX_INFLIGHT (cap: 200)
    `--> If capped: raises KernelError (Fail-Closed admission control)
       |
       v
[TaskKernel State Transitions]
  1. kernel.create_task(...)                        --> State: CREATED
  2. kernel.transition(...) -> PLANNING -> READY    --> State: READY
  3. kernel.transition(...) -> QUEUED               --> State: QUEUED
  4. kernel.claim(...)                              --> State: LEASED
  5. kernel.start(...)                              --> State: RUNNING
  6. kernel.idempotency_claim("rag-read", ...)      --> Idempotency: CLAIMED
  7. kernel.checkpoint(..., "RUNNING", ...)         --> Checkpoint written
       |
       v
[Subsystem Side Effects]
  LLM Gateway chat invocation + RAG context retrieval + RealityJudge validation
       |
       v
[Final Verdict & Verification Gate]
  finalize() transitions task -> VERIFYING
  verify_response() evaluates:
    - RealityJudge.judge_async() semantic grounding
    - grounded_ratio against provided context
    - Governance decision == "UPHOLD"
    - Absence of ungrounded web fallback
       |
       +-----------------------------------------------+
       v                                               v
[Verdict: VERIFIED]                             [Verdict: CONTRADICTED / INSUFFICIENT]
- kernel.commit_verification_result(...)        - kernel.transition(..., "HUMAN_REVIEW")
- State -> COMPLETED                            - Response withheld or sanitized
- Event: TASK_COMPLETED                         - Trace logs failure vector
```

---

## 3. Caveats
1. **Source Code Write Restriction**: In compliance with the explorer archetype and project constraints, no production files were modified. All proposals for state synchronization are documented as architectural recommendations.
2. **Local Single-Node Durability Scope**: TaskKernel durability and atomic locking are implemented for single-node SQLite WAL mode with process/thread isolation. Multi-node distributed consensus (e.g. Raft/etcd) is outside the current architecture and has not been tested.
3. **`RETRY_SCHEDULED` Inactivity**: The analysis concluded that `RETRY_SCHEDULED` has 0 incoming transitions in `ALLOWED_TRANSITIONS`. While safe because it never triggers, it remains dead code in the state space.

---

## 4. Conclusion
1. **State Machine Rigor**:
   TaskKernel possesses a highly resilient state machine backed by SQLite WAL with per-thread connections, monotonic fencing tokens, execution-context lease binding (`_LEASE_CONTEXT`), and cryptographic event journal hash-chaining.
2. **Root Cause of Discrepancy (18 vs 15 States)**:
   - The documentation mandate in `AGENTS.md` and `scp-task-kernel-review/SKILL.md` (15 states) reflects the **initial minimal lifecycle design**.
   - Production reality evolved to **18 states** due to:
     - The addition of `RECONCILING` to handle non-blind recovery of ambiguous external side effects (DNA #2 / #26).
     - The addition of `WAITING_APPROVAL` for governance gates on high-consequence actions.
     - The retention of `RETRY_SCHEDULED` as an unused backoff state.
   - **Critical Architectural Inconsistency**:
     `WAITING_APPROVAL` is present in `ALLOWED_TRANSITIONS` but missing from the `STATES` set in `task_kernel.py:17-22`, requiring hardcoded bypass conditions (`if to_state not in STATES and to_state != 'WAITING_APPROVAL':`).
     `RETRY_SCHEDULED` has outgoing transitions but zero incoming transitions, making it unreachable.
3. **Recommended Actions**:
   - Reconcile `STATES` and `ALLOWED_TRANSITIONS` in `scp/task_kernel.py`:
     - Add `"WAITING_APPROVAL"` to `STATES`.
     - Remove the hardcoded `and to_state != 'WAITING_APPROVAL'` bypass in `transition()` and `_transition_fenced_by_bound_lease()`.
     - Either wire incoming transitions to `RETRY_SCHEDULED` from `RECOVERING` for backoff retry, or formally prune `RETRY_SCHEDULED` from the state graph.
   - Update `AGENTS.md`, `GEMINI.md`, and `scp-task-kernel-review/SKILL.md` to document the 17 or 18 active states accurately.

---

## 5. Verification Method

To independently reproduce and verify all observations and conclusions in this report:

1. **Verify State Machine Counts and Definitions**:
   ```pwsh
   python -c "from scp.task_kernel import STATES, ALLOWED_TRANSITIONS; print('STATES count:', len(STATES)); print('ALLOWED_TRANSITIONS keys count:', len(ALLOWED_TRANSITIONS)); print('Difference:', set(ALLOWED_TRANSITIONS.keys()) - STATES)"
   ```
   *Expected output*: `STATES count: 17`, `ALLOWED_TRANSITIONS keys count: 18`, `Difference: {'WAITING_APPROVAL'}`.

2. **Verify 0 Incoming Transitions for `RETRY_SCHEDULED`**:
   ```pwsh
   python -c "from scp.task_kernel import ALLOWED_TRANSITIONS; incoming = [k for k, v in ALLOWED_TRANSITIONS.items() if 'RETRY_SCHEDULED' in v]; print('Incoming to RETRY_SCHEDULED:', incoming)"
   ```
   *Expected output*: `Incoming to RETRY_SCHEDULED: []`.

3. **Execute Full Kernel Test Suite**:
   ```pwsh
   pytest tests/T04_kernel/ -v
   ```
   *Expected output*: 22 passed.

4. **Execute Chaos & Recovery Test Suite**:
   ```pwsh
   pytest tests/T10_recovery/ -v
   ```
   *Expected output*: 9 passed.

5. **Execute Repository Guardrail & Meta-Audit**:
   ```pwsh
   python tools/t00_meta_audit.py
   python tools/verify_scp_test_skill_contract.py
   ```
   *Expected output*: `ALL CHECKS PASSED` and `PASS_WITHIN_SCOPE`.
