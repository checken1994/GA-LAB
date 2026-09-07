# Handoff Report — Explorer 2: Caller Protocols & Bridges Specialist

**Mission**: Investigate and map the caller pipeline (`scp/api/routes/hands_routes.py`, `scp/hands/task_kernel_bridge.py`, `scp/hands/planner.py`) that invokes `HandsExecutor` to enable end-to-end Zero-Trust capability token propagation without parameter dropping.  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_2`  
**Governing Rules**: Zero-Trust PEP, Fail-Closed, Anti-Placebo, FA-01 through FA-10 (specifically FA-05, INV-AUTH-01, INV-AUTH-02, INV-AUTH-03, INV-AUTH-04).  
**Investigation Mode**: STRICTLY READ-ONLY (No production code modifications performed).

---

## 1. Observation

Direct code inspection of the caller pipeline revealed exact lines, signatures, and control flow disconnects across three subsystem boundaries:

### 1.1 `scp/api/routes/hands_routes.py`
1. **Schema Omission (`HandsActionRequest`)** (lines 38–44):
   ```python
   38: class HandsActionRequest(BaseModel):
   39:     action: str = Field(min_length=3, max_length=64)
   40:     params: dict[str, Any] = Field(default_factory=dict)
   41:     capabilityLevel: int = Field(default=0, ge=0, le=5)
   42:     approved: bool = False
   43:     dryRun: bool = False
   ```
   *Observation*: `HandsActionRequest` completely lacks a `capabilityToken` field. An HTTP client attempting to pass a capability token in the JSON request body has the field ignored/rejected.
2. **Schema Omission (`HandsRollbackRequest`)** (lines 46–50):
   ```python
   46: class HandsRollbackRequest(BaseModel):
   47:     checkpointId: str = Field(min_length=8, max_length=128)
   48:     capabilityLevel: int = Field(default=3, ge=0, le=5)
   49:     approved: bool = False
   ```
   *Observation*: Lacks `capabilityToken`.
3. **Schema Omission (`PlannerRollbackRequest`)** (lines 87–90):
   ```python
   87: class PlannerRollbackRequest(BaseModel):
   88:     capabilityLevel: int = Field(default=3, ge=0, le=5)
   89:     approved: bool = False
   ```
   *Observation*: Lacks `capabilityToken`.
4. **Endpoint Token Dropping (`hands_execute`)** (lines 155–161):
   ```python
   155: @router.post("/execute")
   156: @traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_execute")
   157: async def hands_execute(payload: HandsActionRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
   158:     _guard(request, x_scp_pc_token)
   159:     request_key = request.headers.get("X-SCP-Idempotency-Key") or request.headers.get("Idempotency-Key")
   160:     return await _active_bridge().execute(payload.action, payload.params, payload.capabilityLevel, payload.approved, payload.dryRun, request_key=request_key)
   ```
   *Observation*: `hands_execute` calls `_active_bridge().execute(...)` with only 5 arguments + `request_key`. Zero token information is forwarded.
5. **Endpoint Token Dropping (`hands_rollback`)** (lines 163–168):
   ```python
   163: @router.post("/rollback")
   164: @traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="hands_rollback")
   165: async def hands_rollback(payload: HandsRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
   166:     _guard(request, x_scp_pc_token)
   167:     return await _active_bridge().rollback(payload.checkpointId, payload.capabilityLevel, payload.approved)
   ```
   *Observation*: Calls `_active_bridge().rollback(...)` without any token parameter.
6. **Planner Rollback Dropping (`planner_rollback`)** (lines 246–251):
   ```python
   246: @router.post("/planner/{plan_id}/rollback")
   247: @traced_request(_HANDS_ROUTES_LEDGER, require_write=True, action="planner_rollback")
   248: async def planner_rollback(plan_id: str, payload: PlannerRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
   249:     _guard(request, x_scp_pc_token)
   250:     return await _planner.rollback_plan(plan_id, payload.capabilityLevel, payload.approved)
   ```
   *Observation*: Calls `_planner.rollback_plan(...)` without any token parameter.

---

### 1.2 `scp/hands/task_kernel_bridge.py`
1. **Bridge Rollback Missing Parameter** (lines 99–102):
   ```python
   99:  async def rollback(self, checkpoint_id: str, capability_level: int = 3, approved: bool = False) -> dict[str, Any]:
   100: 
   101:     return await self.executor.rollback(checkpoint_id, capability_level, approved)
   ```
   *Observation*: `rollback()` does not accept `capability_token` and calls `self.executor.rollback(...)` without `capability_token`.
2. **Bridge Execute Missing Parameter** (lines 314–330):
   ```python
   314: async def execute(
   315:     self,
   316:     action: str,
   317:     params: dict[str, Any] | None = None,
   318:     capability_level: int = 0,
   319:     approved: bool = False,
   320:     dry_run: bool = False,
   321:     request_key: str | None = None,
   322: ) -> dict[str, Any]:
   ```
   *Observation*: Does not accept `capability_token`.
3. **Non-mutating / Dry-run Dispatch Drops Token** (lines 336–338):
   ```python
   336: if not definition.mutates_state or dry_run:
   337: 
   338:     return await self.executor.execute(action, params, capability_level, approved, dry_run)
   ```
   *Observation*: Calls `self.executor.execute(...)` without `capability_token`.
4. **Mutating Action Driver Dispatch Drops Token** (lines 480–484):
   ```python
   480: try:
   481: 
   482:     result = await self.executor.execute(action, params, capability_level, approved, False)
   ```
   *Observation*: Calls `self.executor.execute(...)` without `capability_token`.
5. **Critical Defect: `_policy_blocked_before_dispatch` False Fallthrough** (lines 161–188):
   ```python
   161: def _policy_blocked_before_dispatch(result: dict[str, Any]) -> bool:
   162: 
   163:     error = str(result.get("error", "")).lower()
   164: 
   165:     return any(
   166:         marker in error
   167:         for marker in (
   168:             "unknown hands action",
   169:             "capability token is revoked",
   170:             "capability revoked before dispatch",
   171:             "kill switch is engaged",
   172:             "requires capability",
   173:             "explicit approval required",
   174:             "outside safe workspace",
   175:         )
   176:     )
   ```
   *Observation*: When `HandsExecutor` fails closed with `CapabilityRequiredError` or `CapabilityScopeMismatchError`, none of the 7 hardcoded string markers match because `"capability required"` has a space whereas `"capabilityrequirederror"` does not, and `"capabilityscopemismatcherror"` / `"scope mismatch"` is completely absent. Consequently, line 490 evaluates to `False`, and execution falls through to line 564:
   ```python
   564: return self._unknown_result(
   565:     task_id,
   566:     lease.lease_id,
   567:     action,
   568:     planned_action,
   569:     logical_key,
   570:     str(result.get("error") or "Mutating Hands result was not verified; reconcile required"),
   571:     checkpoint_id,
   572: )
   ```
   *Consequence*: A clean pre-dispatch authorization rejection is erroneously classified as an `UNKNOWN` post-dispatch mutation, permanently locking the kernel task into an `UNKNOWN` reconciliation loop!

---

### 1.3 `scp/hands/planner.py`
1. **Token Dropping in Sequential Planner (`_run_plan_locked`)** (line 479):
   ```python
   478: try:
   479:     last_result = await self.executor.execute(step["action"], step.get("params", {}), requested_capability, request_approved, dry_run or bool(step.get("dryRun", False)))
   480: except Exception as exc:
   ```
   *Observation*: `_run_plan_locked` receives `capability_token: str = ""` at line 425, but line 479 calls `self.executor.execute(...)` with only 5 positional arguments. `capability_token` is dropped!
2. **Token Dropping in DAG Planner (`_run_dag_step`)** (line 573):
   ```python
   572: try:
   573:     last_result = await self.executor.execute(step["action"], step.get("params", {}), requested_capability, request_approved, dry_run or bool(step.get("dryRun", False)))
   574: except Exception as exc:
   ```
   *Observation*: `_run_dag_step` receives `capability_token: str = ""` at line 550, but line 573 drops it completely before dispatching to `self.executor.execute`.
3. **Token Dropping in Plan Rollback (`rollback_plan`)** (line 782):
   ```python
   773: async def rollback_plan(self, plan_id: str, capability_level: int = 3, approved: bool = False) -> dict[str, Any]:
   ...
   782:     result = await self.executor.rollback(str(checkpoint_id), capability_level, approved)
   ```
   *Observation*: `rollback_plan` drops token when calling `self.executor.rollback`.
4. **Type Crash Risk with `verify_token`** (lines 457 & 553):
   ```python
   457: requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0))) if verify_token(capability_token).get("valid", False) else min(int(capability_level), int(step.get("capabilityLevel", 0)))
   ```
   In `scp/core/capability_token.py` (lines 31–32):
   ```python
   31: def verify_token(token: str, required_scope: str = "*") -> dict:
   32:     if not token or "." not in token:
   ```
   *Observation*: If a caller passes a `CapabilityToken` dataclass instance or a dict, `"." not in token` raises `TypeError: argument of type 'CapabilityToken' is not iterable`.

---

## 2. Logic Chain

1. **Premise 1 (Self-Granting Root Cause)**: `HandsExecutor.execute` (line 111) and `rollback` (line 326) currently execute `capability_token = capability_token or self.capability_authority.issue(...)`. This violates Rule FA-05 ("Tử huyệt bạo chúa" / self-granting authority).
2. **Premise 2 (Why Self-Granting Existed)**: `HandsExecutor` instituted this fallback because upstream callers (`hands_routes.py`, `task_kernel_bridge.py`, `planner.py`) drop or fail to accept `capability_token`. If line 111 is deleted without updating callers, every caller request terminates in a fail-closed error.
3. **Inference 1 (API Layer Requirement)**:
   - `HandsActionRequest`, `HandsRollbackRequest`, and `PlannerRollbackRequest` must accept `capabilityToken: Any = None`.
   - Over HTTP/JSON, clients may supply tokens as: (a) JSON object `{"subject": "hands:action", "epoch": 0, "token_id": "...", "issued_at": ...}`, (b) JSON stringified dict, or (c) Python `CapabilityToken` instance.
   - A universal deserializer `parse_capability_token(raw: Any) -> CapabilityToken | None` is needed to safely normalize inputs fail-closed.
4. **Inference 2 (Bridge Responsibility & Invariant INV-AUTH-01)**:
   - *Should the bridge generate tokens, or should callers pass tokens to the bridge?*
   - Under Zero-Trust and Separation of Concerns: The bridge is a TaskKernel lifecycle wrapper and execution agent; it is **NOT** an authority or Policy Decision Point (PDP).
   - The bridge must **NEVER** mint tokens. Callers (API clients, agent orchestrators, test runners) must obtain an authorized token from the authority and supply it to `bridge.execute` / `bridge.rollback`.
   - The bridge must accept `capability_token` as an optional parameter (defaulting to `None`), use `token.epoch` in the TaskKernel checkpoint, and pass `capability_token` downstream to `self.executor.execute` / `rollback`.
5. **Inference 3 (Bridge Pre-Dispatch Classification)**:
   - If a request is rejected pre-dispatch by `HandsExecutor` due to missing or mismatched capability (`CapabilityRequiredError` or `CapabilityScopeMismatchError`), `_policy_blocked_before_dispatch` must return `True`.
   - This ensures the TaskKernel transitions the task to `FAILED` (`hands_policy_denied_before_dispatch`), avoiding a catastrophic spurious transition to `UNKNOWN`.
6. **Inference 4 (Planner Multi-Step Token Threading & Invariant INV-AUTH-02)**:
   - In SCP-Omega, tokens are scoped to actions (`subject="hands:<action>"`). In a multi-step plan, step 1 (`pc.status`) and step 2 (`pc.write_file`) require different tokens.
   - `HandsPlanner` must support step-level tokens:
     1. Step definition token: `step.get("capabilityToken")` or `step.get("capability_token")`
     2. Plan-level token map: `capability_token[step["stepId"]]` or `capability_token[step["action"]]` (when `capability_token` is a dict)
     3. Plan-level scalar token fallback: `capability_token` (when valid for the step's action)
   - `HandsPlanner` must thread the resolved token to `self.executor.execute(..., capability_token=step_token)`.
   - `rollback_plan` must accept `capability_token` and thread it to `self.executor.rollback(..., capability_token=token)`.

---

## 3. Caveats

1. **Token Standard Divergence in Codebase**:
   `scp/core/capability_token.py` implements HMAC-SHA256 string tokens (`payload_b64.signature`), whereas `scp/security/capability_epoch.py` implements epoch-based dataclass tokens (`CapabilityToken(subject, epoch, token_id, issued_at)`).
   `HandsExecutor` and `os_sandbox.py` strictly use `scp/security/capability_epoch.py`.
   `HandsPlanner` previously imported `verify_token` from `scp.core.capability_token`. To prevent format conflicts, `parse_capability_token` must handle both formats or gracefully distinguish them without throwing exceptions.
2. **Backward Compatibility with Unmodified Tests**:
   Existing tests in `tests/T04_kernel/test_kernel_p1_regressions.py` and `tests/T09_golden_task/test_golden_a_agent_os.py` call `bridge.execute(...)` without a token. When `HandsExecutor` self-granting is eliminated, these tests will legitimately fail closed unless they are updated to supply an authorized token issued by `CapabilityAuthority`. This is expected and required by Rule FA-07 and DNA #22 (`PASS != TRUE`).

---

## 4. Conclusion & Precise Interface Mapping

### 4.1 Shared Token Deserializer: `scp/security/capability_epoch.py`
Add `parse_capability_token(token: Any) -> CapabilityToken | None` to `scp/security/capability_epoch.py`:
```python
def parse_capability_token(token: Any) -> CapabilityToken | None:
    if token is None or token == "":
        return None
    if isinstance(token, CapabilityToken):
        return token
    if isinstance(token, str):
        token = token.strip()
        if not token:
            return None
        try:
            parsed = json.loads(token)
            if isinstance(parsed, dict):
                token = parsed
            else:
                return None
        except Exception:
            return None
    if isinstance(token, dict):
        try:
            return CapabilityToken(
                subject=str(token.get("subject", "")),
                epoch=int(token.get("epoch", 0)),
                token_id=str(token.get("token_id") or token.get("tokenId", "")),
                issued_at=float(token.get("issued_at") or token.get("issuedAt", 0.0)),
            )
        except (ValueError, TypeError):
            return None
    return None
```
Also add `to_dict(self) -> dict[str, Any]` to `CapabilityToken` dataclass.

---

### 4.2 Exact Function Signatures & Argument Mappings

#### A. `scp/api/routes/hands_routes.py`

| Target Symbol | Location | Proposed Code / Signature | Purpose / Default |
|---|---|---|---|
| `HandsActionRequest` | Lines 38–44 | ```python
class HandsActionRequest(BaseModel):
    action: str = Field(min_length=3, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    capabilityLevel: int = Field(default=0, ge=0, le=5)
    approved: bool = False
    dryRun: bool = False
    capabilityToken: Any = Field(default=None, description="Zero-Trust capability token")
``` | Accept token via JSON payload. Default: `None`. |
| `HandsRollbackRequest` | Lines 46–50 | ```python
class HandsRollbackRequest(BaseModel):
    checkpointId: str = Field(min_length=8, max_length=128)
    capabilityLevel: int = Field(default=3, ge=0, le=5)
    approved: bool = False
    capabilityToken: Any = Field(default=None, description="Zero-Trust capability token")
``` | Accept token for rollback. Default: `None`. |
| `PlannerRollbackRequest` | Lines 87–90 | ```python
class PlannerRollbackRequest(BaseModel):
    capabilityLevel: int = Field(default=3, ge=0, le=5)
    approved: bool = False
    capabilityToken: Any = Field(default=None, description="Zero-Trust capability token")
``` | Accept token for plan rollback. Default: `None`. |
| `hands_execute` | Lines 155–161 | ```python
async def hands_execute(payload: HandsActionRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    request_key = request.headers.get("X-SCP-Idempotency-Key") or request.headers.get("Idempotency-Key")
    token = parse_capability_token(payload.capabilityToken)
    return await _active_bridge().execute(
        payload.action,
        payload.params,
        payload.capabilityLevel,
        payload.approved,
        payload.dryRun,
        request_key=request_key,
        capability_token=token,
    )
``` | Parse token and forward to `bridge.execute`. |
| `hands_rollback` | Lines 163–168 | ```python
async def hands_rollback(payload: HandsRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    token = parse_capability_token(payload.capabilityToken)
    return await _active_bridge().rollback(
        payload.checkpointId,
        payload.capabilityLevel,
        payload.approved,
        capability_token=token,
    )
``` | Parse token and forward to `bridge.rollback`. |
| `planner_rollback` | Lines 246–251 | ```python
async def planner_rollback(plan_id: str, payload: PlannerRollbackRequest, request: Request, x_scp_pc_token: str | None = Header(default=None)) -> dict[str, Any]:
    _guard(request, x_scp_pc_token)
    token = parse_capability_token(payload.capabilityToken)
    return await _planner.rollback_plan(
        plan_id,
        payload.capabilityLevel,
        payload.approved,
        capability_token=token,
    )
``` | Forward token to `_planner.rollback_plan`. |

---

#### B. `scp/hands/task_kernel_bridge.py`

| Target Symbol | Location | Proposed Code / Signature | Purpose / Default |
|---|---|---|---|
| `rollback` | Line 99 | ```python
async def rollback(
    self,
    checkpoint_id: str,
    capability_level: int = 3,
    approved: bool = False,
    capability_token: CapabilityToken | Any = None,
) -> dict[str, Any]:
    token = parse_capability_token(capability_token)
    return await self.executor.rollback(
        checkpoint_id,
        capability_level,
        approved,
        capability_token=token,
    )
``` | Forward token to `executor.rollback`. Default: `None`. |
| `execute` | Line 314 | ```python
async def execute(
    self,
    action: str,
    params: dict[str, Any] | None = None,
    capability_level: int = 0,
    approved: bool = False,
    dry_run: bool = False,
    request_key: str | None = None,
    capability_token: CapabilityToken | Any = None,
) -> dict[str, Any]:
``` | Accept token. Default: `None`. |
| Non-mutating branch | Line 338 | ```python
if not definition.mutates_state or dry_run:
    return await self.executor.execute(
        action,
        params,
        capability_level,
        approved,
        dry_run,
        capability_token=token,
    )
``` | Forward token on non-mutating/dry-run path. |
| Checkpoint call | Line 441 | ```python
checkpoint_id = self.kernel.checkpoint(
    task_id,
    lease.lease_id,
    action,
    "WAITING_TOOL",
    planned_action,
    token.epoch if token else self._capability_epoch(self.executor),
    logical_key,
    pre_observation_ref=f"hands://{task_id}/pre",
)
``` | Store actual token epoch in TaskKernel checkpoint. |
| Mutating dispatch | Line 482 | ```python
result = await self.executor.execute(
    action,
    params,
    capability_level,
    approved,
    False,
    capability_token=token,
)
``` | Forward token to executor driver dispatch. |
| `_policy_blocked_before_dispatch` | Lines 161–188 | ```python
@staticmethod
def _policy_blocked_before_dispatch(result: dict[str, Any]) -> bool:
    error = str(result.get("error", "")).lower()
    return any(
        marker in error
        for marker in (
            "unknown hands action",
            "capability token is revoked",
            "capability revoked before dispatch",
            "capabilityrequired",
            "capability required",
            "capabilityscopemismatch",
            "scope mismatch",
            "caller must provide an authorized capability token",
            "kill switch is engaged",
            "requires capability",
            "explicit approval required",
            "outside safe workspace",
            "unauthorized",
        )
    )
``` | **CRITICAL FIX**: Prevent pre-dispatch capability rejection from falsely transitioning task to `UNKNOWN`. |

---

#### C. `scp/hands/planner.py`

| Target Symbol | Location | Proposed Code / Signature | Purpose / Default |
|---|---|---|---|
| `run_plan` | Line 401 | ```python
async def run_plan(
    self,
    plan_id: str,
    capability_level: int = 0,
    approved: bool = False,
    dry_run: bool = False,
    stop_on_failure: bool = True,
    capability_token: Any = "",
) -> dict[str, Any]:
``` | Accept `Any` token type (str, dict, CapabilityToken). Default: `""`. |
| `_run_plan_locked` | Line 425 | ```python
async def _run_plan_locked(
    self,
    plan_id: str,
    capability_level: int = 0,
    approved: bool = False,
    dry_run: bool = False,
    stop_on_failure: bool = True,
    capability_token: Any = "",
) -> dict[str, Any]:
``` | Thread resolved step token to executor. |
| Step token resolution | Lines 456–480 | ```python
# Resolve token for step:
step_token = (
    step.get("capabilityToken")
    or step.get("capability_token")
    or (capability_token.get(step["stepId"]) if isinstance(capability_token, dict) else None)
    or (capability_token.get(step["action"]) if isinstance(capability_token, dict) else None)
    or capability_token
)
parsed_step_token = parse_capability_token(step_token)

# Safe capability verification:
token_is_valid = (
    parsed_step_token is not None
    or (isinstance(capability_token, str) and "." in capability_token and verify_token(capability_token).get("valid", False))
)
requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0))) if token_is_valid else min(int(capability_level), int(step.get("capabilityLevel", 0)))

# Dispatch with token:
last_result = await self.executor.execute(
    step["action"],
    step.get("params", {}),
    requested_capability,
    request_approved,
    dry_run or bool(step.get("dryRun", False)),
    capability_token=parsed_step_token,
)
``` | Resolves per-step token and passes it to `self.executor.execute`. |
| `_run_dag_step` | Lines 550–575 | Same step token resolution and dispatch as `_run_plan_locked`. | Passes `capability_token=parsed_step_token` to `self.executor.execute`. |
| `rollback_plan` | Line 773 | ```python
async def rollback_plan(
    self,
    plan_id: str,
    capability_level: int = 3,
    approved: bool = False,
    capability_token: Any = None,
) -> dict[str, Any]:
    parsed_token = parse_capability_token(capability_token)
    ...
    result = await self.executor.rollback(
        str(checkpoint_id),
        capability_level,
        approved,
        capability_token=parsed_token,
    )
``` | Accepts token and passes to `self.executor.rollback`. |

---

## 5. Verification Method

To independently verify these findings and prove the fix strategy:

1. **Probe Verification (Baseline vs Guarded)**:
   Run the adversarial probe script:
   ```powershell
   python tools/probes/probe_hands_authority_flaws.py
   ```
   - Baseline behavior: Sub-test 1 & 2 fail with AssertionError (RED), proving baseline vulnerability.
   - Guarded PEP behavior: Sub-test 3 passes (GREEN), confirming non-placebo sensitivity.
2. **Contract & AST Inspection**:
   Inspect the three caller files to verify all parameter dropped points:
   - `scp/api/routes/hands_routes.py`: Check `HandsActionRequest.model_fields` and `HandsRollbackRequest.model_fields`.
   - `scp/hands/task_kernel_bridge.py`: Check `inspect.signature(TaskKernelHandsBridge.execute)` and `inspect.signature(TaskKernelHandsBridge.rollback)`.
   - `scp/hands/planner.py`: Check call sites of `self.executor.execute` at line 479 and 573.
3. **End-to-End Test Suite Command**:
   After implementation of GAP-07 by the builder agent:
   ```powershell
   pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v
   pytest tests/ -q
   python tools/t00_meta_audit.py
   ```
   **Invalidation Condition**: If any call to `HandsExecutor.execute()` succeeds when `capability_token is None`, the fix is invalid (FA-05 violation). If `TaskKernelHandsBridge.execute()` marks a task as `UNKNOWN` when rejected due to missing capability, the fix is invalid.
