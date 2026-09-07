# HANDOFF REPORT: TEST SUITE IMPACT & MIGRATION MAP (GAP-07)

**Auditor / Specialist**: Explorer 3 (Test Suite Impact & Migration Specialist)  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_3`  
**Target Milestone**: GAP-07 — HandsExecutor Self-Granting Authority Eradication (FA-05 Resolution)  
**Governing Invariants**: INV-AUTH-01 (Disjoint Authority Boundary), INV-AUTH-02 (Scoped Subject Binding), INV-AUTH-03 (Pre-Dispatch Fail-Closed PEP Gate), FA-01 through FA-10  
**Timestamp**: 2026-09-07T03:20:00Z  

---

## 1. Observation

### 1.1 Baseline Test Suite Execution (Level 1 Empirical Terminal Capture)
On branch `omega/gap-01-remediation` (working directory `c:\Users\check\Downloads\scp`):
```text
$ python -m pytest tests/ -q
C:\Users\check\AppData\Local\Programs\Python\Python312\Lib\site-packages\requests\__init__.py:113: RequestsDependencyWarning: urllib3 (2.7.0) or chardet (6.0.0.post1)/charset_normalizer (3.4.3) doesn't match a supported version!
  warnings.warn(
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 48%]
........................................................................ [ 65%]
........................................................................ [ 81%]
........................................................................ [ 97%]
.........                                                                [100%]
441 passed in 106.57s (0:01:46)
Exit code: 0
```
- Total test count collected: **441 tests**.
- Total passing: **441 passed**.
- Failures / Errors / Skips: **0**.

---

### 1.2 Exhaustive Call Site Inventory Across `tests/`
Every test file across `tests/` was grepped and analyzed for calls to:
- `HandsExecutor.execute` or `HandsExecutor.rollback`
- `TaskKernelHandsBridge.execute` or `TaskKernelHandsBridge.rollback`
- `POST /v3/hands/execute` or `POST /v3/hands/rollback`
- `HandsPlanner.run_plan` or `create_plan`

| Target Interface | Files in `tests/` Calling Interface | Exact Test Functions | Total Call Sites |
|---|---|---|---|
| `HandsExecutor.execute` (via `bridge.execute`) | `tests/T04_kernel/test_kernel_p1_regressions.py`<br>`tests/T09_golden_task/test_golden_a_agent_os.py` | 1. `test_bridge_duplicate_request_returns_replayed_response`<br>2. `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`<br>3. `test_golden_a_agent_os_real_execution_flow` | 5 call sites across 3 tests |
| `HandsExecutor.rollback` | **None** | **None** | 0 |
| `TaskKernelHandsBridge.rollback` | **None** | **None** | 0 |
| `POST /v3/hands/execute` | **None** (Only route string check in `test_api_route_profile.py`) | **None** | 0 |
| `POST /v3/hands/rollback` | **None** | **None** | 0 |
| `HandsPlanner.run_plan` | **None** (Not called anywhere in `tests/`) | **None** | 0 |

---

### 1.3 Detailed Call Site Observations & Failure Preconditions

#### Call Site Group 1: `tests/T04_kernel/test_kernel_p1_regressions.py`
File: `tests/T04_kernel/test_kernel_p1_regressions.py`  
Helper: `_bridge_with_executor(tmp_path: Path)` (lines 41–46):
```python
41: def _bridge_with_executor(tmp_path: Path) -> tuple[TaskKernelHandsBridge, Path]:
42:     workspace = tmp_path / "workspace"
43:     workspace.mkdir()
44:     executor = HandsExecutor(controller=PCController(working_dir=workspace))
45:     bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")
46:     return bridge, workspace
```
- **Observation 1.3.1 (`test_bridge_duplicate_request_returns_replayed_response`)**:
  - Line 96–103:
    ```python
    first = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": content},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )
    ```
  - Line 105: `assert first.get("success") is True, f"first execution failed: {first}"`
  - Line 111–118:
    ```python
    replay = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "MUTATED_BY_REPLAY"},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )
    ```
  - Precondition failure: Neither call provides `capability_token`. Both rely on `HandsExecutor.execute` (line 111) self-minting a token. Once line 111 is removed and missing token is rejected fail-closed, `first.get("success")` returns `False`, causing line 105 to raise `AssertionError`.

- **Observation 1.3.2 (`test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`)**:
  - Lines 293–297:
    ```python
    async def slow_execute(action, params, capability_level, approved, dry_run):
        await asyncio.sleep(2.4)  # > 2 full lease TTLs
        return await real_execute(action, params, capability_level, approved, dry_run)

    executor.execute = slow_execute
    ```
  - Lines 312–320:
    ```python
    result = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": content},
            capability_level=3,
            approved=True,
            request_key=f"p1-slow-{uuid.uuid4().hex}",
        )
    )
    ```
  - Line 322: `assert result.get("success") is True, f"slow dispatch failed: {result}"`
  - Precondition failure: `slow_execute` omits `capability_token` from its parameter signature. When `TaskKernelHandsBridge.execute` forwards `capability_token`, a `TypeError` occurs, or if dropped, `real_execute` receives `None` and returns `CapabilityRequiredError`.

---

#### Call Site Group 2: `tests/T09_golden_task/test_golden_a_agent_os.py`
File: `tests/T09_golden_task/test_golden_a_agent_os.py`
- **Observation 1.3.3 (`test_golden_a_agent_os_real_execution_flow`)**:
  - Lines 36–38:
    ```python
    workspace.mkdir()
    executor = HandsExecutor(controller=PCController(working_dir=workspace))
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")
    ```
  - Lines 44–52 (Primary Dispatch):
    ```python
    result = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": content},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )
    ```
  - Line 54: `assert result.get("success") is True`
  - Lines 94–102 (Replay Idempotency Dispatch):
    ```python
    replay = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "overwritten_by_replay"},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )
    ```
  - Precondition failure: Both calls pass `capability_token=None`. In the baseline, this test passed because `HandsExecutor` minted its own token on the fly. Under Zero-Trust fail-closed enforcement, `result.get("success")` returns `False`, crashing the golden task.

---

### 1.4 Non-Affected Capability and Contract Tests
The following tests in `tests/T03_capability/` were audited to verify that changing `CapabilityAuthority.validate` does NOT cause side-effect breakages:
- `tests/T03_capability/test_risk_intelligence_contract.py:103`: Calls `cap_auth.validate(token)`. Valid because `required_subject` defaults to `None`.
- `tests/T03_capability/test_os_sandbox.py:8`: Calls `pie.execute_bounded(token, ...)` which validates epoch. Valid.
- `tests/T09_golden_task/test_golden_risk_containment_e2e.py:26`: Calls `cap_auth.validate(worker_token)`. Valid.
All 43 tests in `tests/T03_capability/` pass (verified in 1.09s).

---

## 2. Logic Chain

1. **Premise 1 (INV-AUTH-01 & FA-05 Enforcement)**:
   In `HandsExecutor.execute` (line 111) and `HandsExecutor.rollback` (line 326), fallback self-issuance (`capability_token = capability_token or self.capability_authority.issue(...)`) must be permanently deleted. When `capability_token is None`, the executor must return `{"success": False, "action": action, "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)", "verification": {"passed": False}}`.

2. **Premise 2 (Call-Stack Propagation)**:
   `TaskKernelHandsBridge.execute` (line 314) and `TaskKernelHandsBridge.rollback` (line 99) must accept `capability_token: CapabilityToken | None = None` and forward it directly to `self.executor.execute(..., capability_token=capability_token)` and `self.executor.rollback(..., capability_token=capability_token)`.

3. **Inference 1 (Test Failure Consequence)**:
   From Observations 1.3.1, 1.3.2, and 1.3.3: Exactly 3 tests call `bridge.execute()` without providing `capability_token`. If production code is updated without migrating these 3 tests, all 3 tests will immediately fail `assert result.get("success") is True`.

4. **Inference 2 (Preservation of Test Strictness — FA-01 & FA-02)**:
   Rule FA-01 strictly prohibits loosening assertions (e.g. changing `assert result.get("success") is True` to `assert ... or "CapabilityRequiredError"`).
   Rule FA-02 strictly prohibits skipping, xfailing, or deleting any test.
   Therefore, the tests must be migrated by **providing a genuine, authoritative `CapabilityToken`** issued by `CapabilityAuthority` with the exact required subject `hands:pc.write_file`.

5. **Inference 3 (Lineage & Architecture Compliance)**:
   The tests represent the caller / orchestrator / PDP. The test harness must instantiate `CapabilityAuthority` (acting as the Policy Decision Point), issue the token, and pass it to the bridge / executor (the Policy Enforcement Point). This converts what was previously a manufactured pass into a genuine Zero-Trust Level C verification proof.

---

## 3. Caveats

- **No HTTP API Client Tests in `tests/`**: There are currently zero end-to-end HTTP client tests calling `POST /v3/hands/execute` or `POST /v3/hands/rollback` (only schema and route profile AST assertions exist in `tests/T02_contract/`). The API route changes in `scp/api/routes/hands_routes.py` will not break existing pytest cases, but an API contract integration test should be added as part of implementation.
- **`HandsPlanner` Callers**: `HandsPlanner.run_plan` is currently not called anywhere in `tests/`. Its migration in `scp/hands/planner.py` (forwarding `capability_token` to `executor.execute`) is required by architecture invariants, but will not impact current pytest nodeids.
- **Read-Only Scope of Explorer 3**: In accordance with the Teamwork Explorer archetype and FA-06, zero production code or test files in `tests/` or `scp/` were mutated during this investigation.

---

## 4. Conclusion & Migration Strategy Map

### 4.1 Affected Tests Summary Table

| Test File | Test Name | Vulnerable Call | Root Cause of Failure | Migration Action |
|---|---|---|---|---|
| `tests/T04_kernel/test_kernel_p1_regressions.py` | `test_bridge_duplicate_request_returns_replayed_response` | Lines 97 & 112: `bridge.execute(...)` | Omits `capability_token` | Issue token `hands:pc.write_file` from `cap_auth` and pass `capability_token=token` to both `bridge.execute` calls. Preserve all 9 assertions. |
| `tests/T04_kernel/test_kernel_p1_regressions.py` | `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch` | Line 293: `slow_execute(...)`<br>Line 313: `bridge.execute(...)` | `slow_execute` signature lacks token parameter; call omits token | Update `slow_execute` to accept and forward `capability_token=None, **kwargs`. Issue token `hands:pc.write_file` and pass `capability_token=token`. Preserve all 7 assertions. |
| `tests/T09_golden_task/test_golden_a_agent_os.py` | `test_golden_a_agent_os_real_execution_flow` | Lines 45 & 95: `bridge.execute(...)` | Omits `capability_token` | Instantiate `CapabilityAuthority`, issue token `hands:pc.write_file`, pass `capability_token=token` to both `bridge.execute` calls. Preserve all 14 assertions. |

---

### 4.2 Exact Code Migration Snippets (Before -> After)

#### Migration 1: `tests/T04_kernel/test_kernel_p1_regressions.py`
```python
# ---------------------------------------------------------------------------
# BEFORE (Lines 30-46)
# ---------------------------------------------------------------------------
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.task_kernel import ALLOWED_TRANSITIONS, CheckpointCorrupt, TaskKernel


def _bridge_with_executor(tmp_path: Path) -> tuple[TaskKernelHandsBridge, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = HandsExecutor(controller=PCController(working_dir=workspace))
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")
    return bridge, workspace

# ---------------------------------------------------------------------------
# AFTER (Lines 30-51)
# ---------------------------------------------------------------------------
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.security.capability_epoch import CapabilityAuthority
from scp.task_kernel import ALLOWED_TRANSITIONS, CheckpointCorrupt, TaskKernel


def _bridge_with_executor(tmp_path: Path) -> tuple[TaskKernelHandsBridge, Path, CapabilityAuthority]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cap_state = tmp_path / "capability_state.json"
    cap_auth = CapabilityAuthority(cap_state)
    executor = HandsExecutor(
        controller=PCController(working_dir=workspace),
        capability_authority=cap_auth,
        data_dir=tmp_path / "hands_data",
    )
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")
    return bridge, workspace, cap_auth
```

In `test_bridge_duplicate_request_returns_replayed_response`:
```python
# ---------------------------------------------------------------------------
# BEFORE (Lines 89-118)
# ---------------------------------------------------------------------------
def test_bridge_duplicate_request_returns_replayed_response(tmp_path):
    bridge, workspace = _bridge_with_executor(tmp_path)
    try:
        target = workspace / "replay_artifact.txt"
        content = "original_state_written_once"
        request_key = f"p1-replay-{uuid.uuid4().hex}"

        first = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": content},
                capability_level=3,
                approved=True,
                request_key=request_key,
            )
        )
        assert first.get("success") is True, f"first execution failed: {first}"
        task_id = first["kernel"]["taskId"]

        kernel = TaskKernel(str(tmp_path / "kernel.sqlite3"))
        events_before = len(kernel.get_events(task_id))

        replay = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "MUTATED_BY_REPLAY"},
                capability_level=3,
                approved=True,
                request_key=request_key,
            )
        )

# ---------------------------------------------------------------------------
# AFTER (Lines 89-122)
# ---------------------------------------------------------------------------
def test_bridge_duplicate_request_returns_replayed_response(tmp_path):
    bridge, workspace, cap_auth = _bridge_with_executor(tmp_path)
    try:
        target = workspace / "replay_artifact.txt"
        content = "original_state_written_once"
        request_key = f"p1-replay-{uuid.uuid4().hex}"
        token = cap_auth.issue("hands:pc.write_file")

        first = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": content},
                capability_level=3,
                approved=True,
                request_key=request_key,
                capability_token=token,
            )
        )
        assert first.get("success") is True, f"first execution failed: {first}"
        task_id = first["kernel"]["taskId"]

        kernel = TaskKernel(str(tmp_path / "kernel.sqlite3"))
        events_before = len(kernel.get_events(task_id))

        replay = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": "MUTATED_BY_REPLAY"},
                capability_level=3,
                approved=True,
                request_key=request_key,
                capability_token=token,
            )
        )
```

In `test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch`:
```python
# ---------------------------------------------------------------------------
# BEFORE (Lines 282-321)
# ---------------------------------------------------------------------------
def test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch(tmp_path):
    bridge, workspace = _bridge_with_executor(tmp_path)
    try:
        bridge.lease_ttl_seconds = 1.0

        executor = bridge.executor
        real_execute = executor.execute

        async def slow_execute(action, params, capability_level, approved, dry_run):
            await asyncio.sleep(2.4)  # > 2 full lease TTLs
            return await real_execute(action, params, capability_level, approved, dry_run)

        executor.execute = slow_execute
...
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": content},
                capability_level=3,
                approved=True,
                request_key=f"p1-slow-{uuid.uuid4().hex}",
            )
        )

# ---------------------------------------------------------------------------
# AFTER (Lines 282-325)
# ---------------------------------------------------------------------------
def test_bridge_heartbeat_keeps_lease_alive_across_slow_dispatch(tmp_path):
    bridge, workspace, cap_auth = _bridge_with_executor(tmp_path)
    try:
        bridge.lease_ttl_seconds = 1.0

        executor = bridge.executor
        real_execute = executor.execute

        async def slow_execute(action, params, capability_level, approved, dry_run, capability_token=None, **kwargs):
            await asyncio.sleep(2.4)  # > 2 full lease TTLs
            return await real_execute(action, params, capability_level, approved, dry_run, capability_token=capability_token, **kwargs)

        executor.execute = slow_execute
...
        token = cap_auth.issue("hands:pc.write_file")
        result = asyncio.run(
            bridge.execute(
                action="pc.write_file",
                params={"path": str(target), "content": content},
                capability_level=3,
                approved=True,
                request_key=f"p1-slow-{uuid.uuid4().hex}",
                capability_token=token,
            )
        )
```

---

#### Migration 2: `tests/T09_golden_task/test_golden_a_agent_os.py`
```python
# ---------------------------------------------------------------------------
# BEFORE (Lines 8-52 and 94-102)
# ---------------------------------------------------------------------------
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.task_kernel import TaskKernel
from scp.verifier import IndependentVerifier


def test_golden_a_agent_os_real_execution_flow(tmp_path):
    """Golden A: create task -> capability -> bounded action -> real observation -> durable evidence."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = HandsExecutor(controller=PCController(working_dir=workspace))
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")

    target = workspace / "golden_artifact.txt"
    content = "real_state_written_by_golden_a"
    request_key = f"golden-a-{uuid.uuid4().hex}"

    result = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": content},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )
    ...
    replay = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "overwritten_by_replay"},
            capability_level=3,
            approved=True,
            request_key=request_key,
        )
    )

# ---------------------------------------------------------------------------
# AFTER (Lines 8-58 and 98-106)
# ---------------------------------------------------------------------------
from scp.hands.hands_executor import HandsExecutor
from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
from scp.pc_control.pc_controller import PCController
from scp.security.capability_epoch import CapabilityAuthority
from scp.task_kernel import TaskKernel
from scp.verifier import IndependentVerifier


def test_golden_a_agent_os_real_execution_flow(tmp_path):
    """Golden A: create task -> capability -> bounded action -> real observation -> durable evidence."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cap_state = tmp_path / "capability_state.json"
    cap_auth = CapabilityAuthority(cap_state)
    executor = HandsExecutor(
        controller=PCController(working_dir=workspace),
        capability_authority=cap_auth,
        data_dir=tmp_path / "hands_data",
    )
    bridge = TaskKernelHandsBridge(executor, db_path=tmp_path / "kernel.sqlite3")

    target = workspace / "golden_artifact.txt"
    content = "real_state_written_by_golden_a"
    request_key = f"golden-a-{uuid.uuid4().hex}"
    token = cap_auth.issue("hands:pc.write_file")

    result = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": content},
            capability_level=3,
            approved=True,
            request_key=request_key,
            capability_token=token,
        )
    )
    ...
    replay = asyncio.run(
        bridge.execute(
            action="pc.write_file",
            params={"path": str(target), "content": "overwritten_by_replay"},
            capability_level=3,
            approved=True,
            request_key=request_key,
            capability_token=token,
        )
    )
```

---

### 4.3 Recommended New Invariant Test File
To satisfy Anti-Placebo and permanently guard against regressions to FA-05, create `tests/T03_capability/test_hands_authority_pep.py`:
- `test_hands_executor_rejects_missing_token_fail_closed`: Verifies that `execute(action="pc.write_file", capability_token=None)` returns `success=False`, `error="CapabilityRequiredError..."`, and creates no file on disk.
- `test_hands_executor_rejects_scope_mismatch_fail_closed`: Verifies that a token issued for `"hands:pc.status"` passed to `execute("pc.write_file", ...)` returns `success=False`, `error="CapabilityScopeMismatchError..."`, and creates no file on disk.
- `test_hands_executor_rejects_revoked_epoch`: Verifies that after `cap_auth.revoke()`, dispatch is rejected fail-closed.
- `test_hands_executor_rollback_requires_token`: Verifies that `rollback(..., capability_token=None)` returns `success=False` with `CapabilityRequiredError`.

Adding this file will increase test count from 441 to 445+, strictly satisfying FA-01 and FA-02.

---

## 5. Verification Method

### 5.1 Pre-Migration Baseline Verification
Command to verify existing green baseline:
```bash
python -m pytest tests/ -q
# Output: 441 passed
```

Targeted baseline of affected test files:
```bash
python -m pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v
# Output: 6 passed in 3.37s
```

### 5.2 Post-Migration Verification (To Be Run by Implementer & Victory Auditor)
1. **Adversarial Probe Check**:
   ```bash
   python tools/probes/probe_hands_authority_flaws.py
   # Must PASS all 3 sub-tests with 0 unhandled exceptions.
   ```
2. **Targeted Regression Suite**:
   ```bash
   python -m pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v
   # Must PASS all 6 tests cleanly with valid capability tokens.
   ```
3. **Capability Contract Suite**:
   ```bash
   python -m pytest tests/T03_capability -v
   # Must PASS all 43 tests (or 47 with new PEP tests).
   ```
4. **Full Test Suite Integrity**:
   ```bash
   python -m pytest tests/ -q
   # Must PASS with count >= 441 (no deletions, no skips, no xfails, exit code 0).
   ```
5. **Meta-Audit Integrity Authority**:
   ```bash
   python tools/t00_meta_audit.py
   # Must output: [T00 Meta-Audit] All integrity checks passed (0 new regressions).
   ```

### 5.3 Invalidation Conditions
This analysis and migration plan is invalidated if:
1. Any test is deleted, marked `@pytest.mark.skip`, `@pytest.mark.xfail`, or wrapped in `try/except Exception: pass`.
2. Any assertion in `test_kernel_p1_regressions.py` or `test_golden_a_agent_os.py` is relaxed or modified to accept failure states.
3. `HandsExecutor` retains any internal call to `.issue()` (re-introducing self-granting backdoor).
4. `CapabilityAuthority.validate` ignores `required_subject` when supplied by PEP.
