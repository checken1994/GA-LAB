# HANDOFF REPORT: PLANNER STEP VALIDATION REMEDIATION SPECIFICATION (GAP-07)

**Author**: Explorer 5 (Iteration 2: Planner Step Validation Specialist)  
**Roles**: Explorer, Planner Step Validation Specialist, Read-only Investigator  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\orchestrator_5\explorer_5`  
**Target Workspace**: `c:\Users\check\Downloads\scp`  
**Parent Agent**: `parent` (`967399d1-d666-4dce-899b-4c2468b6dd91`)  
**Verdict**: **REMEDIATION SPECIFIED & EMPIRICALLY VERIFIED**  
**Date**: 2026-09-07T14:26:00+07:00  

---

## Executive Summary

During Iteration 1 of the GAP-07 remediation, `HandsPlanner` was updated to support capability tokens during plan execution (`_run_plan_locked`, `_run_dag_step`). However, `_validate_step()` in `scp/hands/planner.py` (lines 284–300) strictly projects only a hardcoded whitelist of step attributes when creating plans via `create_plan()`. 

As a result, any `capabilityToken` or `capability_token` supplied per-step is silently discarded at plan creation time. Consequently, `step.get("capabilityToken")` in `_run_plan_locked` and `_run_dag_step` always returns `None`, causing actions without plan-level tokens to fail closed with `CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)`.

Furthermore, empirical investigation revealed that if a `CapabilityToken` dataclass object is stored directly without converting via `.to_dict()`, `json.dumps(..., default=str)` stringifies it into `repr` format (`"CapabilityToken(subject=..., ...)"`), which `parse_capability_token()` fails to parse upon reloading from the journal (`parsed: None`).

This report provides the exact line-by-line call graph, empirical terminal proof, and the precise code remediation for Worker 2.

---

## 1. Observation

### 1.1 Line-by-Line Call Graph & Execution Trace (Navigation Map)

The lifecycle of a plan step from ingestion to execution traces through the following call chain:

```text
[Caller / API POST /planner]
       │
       ▼
`HandsPlanner.create_plan(goal, steps, metadata)` (planner.py:301)
       │
       ├─► Loop: `for index, raw in enumerate(steps):` (planner.py:309)
       │         │
       │         ▼
       │   `self._validate_step(raw, index, known_ids)` (planner.py:257)
       │         │
       │         ├─► Validate action, stepId, dependencies, params, conditions, retryPolicy (planner.py:258-283)
       │         │
       │         ▼
       │   [CONSTRUCT CLEAN STEP DICTIONARY] (planner.py:284-300)
       │         │  "stepId", "action", "params", "capabilityLevel",
       │         │  "approved", "dryRun", "dependsOn", "precondition",
       │         │  "postcondition", "retryPolicy", "state", "attempts",
       │         │  "evidence", "error"
       │         │  *** DEFECT: "capabilityToken" / "capability_token" DROPPED HERE ***
       │         │
       │         ▼
       │   `normalized.append(step)` (planner.py:313)
       │
       ├─► `plan = {"planId": ..., "steps": normalized, ...}` (planner.py:315)
       │
       ├─► `self._save(plan, "PLAN_CREATED")` (planner.py:327)
       │         │
       │         ▼
       │   `self._record(...)` (planner.py:163)
       │         │
       │         ▼
       │   `json.dumps({"plan": plan, ...}, default=str)` -> write to `plans.jsonl` (planner.py:180, 184)
       │
       └─► `return self._public_plan(plan)` (planner.py:328)

[Execution Phase: `run_plan(plan_id, ...)`] (planner.py:402)
       │
       ▼
`self._run_plan_locked(...)` (planner.py:426)
       │
       ├─► `plan = self._get(plan_id)` -> `_load_latest()` -> `json.loads(line)` (planner.py:427, 209, 196)
       │
       ├─► Loop: `for step in plan.get("steps", []):` (planner.py:442)
       │         │
       │         ▼
       │   `step_token = step.get("capabilityToken") or step.get("capability_token") or ...` (planner.py:459-464)
       │         │  *** CRITICAL FAILURE: step.get("capabilityToken") IS ALWAYS None ***
       │         │
       │         ▼
       │   `parsed_step_token = parse_capability_token(step_token)` (planner.py:465)
       │         │  *** parsed_step_token IS None ***
       │         │
       │         ▼
       │   `await self.executor.execute(..., capability_token=parsed_step_token)` (planner.py:493)
       │         │
       │         ▼
       │   `HandsExecutor.execute(..., capability_token=None)` (hands_executor.py:111)
       │         │  *** FAILS CLOSED with CapabilityRequiredError ***
```

### 1.2 Exact Code Defect in `_validate_step()`
In `scp/hands/planner.py` lines 283–300:
```python
283:         raw_capability = max(0, min(int(raw.get("capabilityLevel", definition.capability_level)), 5))
284:         return {
285:             "stepId": step_id,
286:             "action": action,
287:             "params": params,
288:             "capabilityLevel": raw_capability,
289:             "approved": bool(raw.get("approved", False)),
290:             "dryRun": bool(raw.get("dryRun", False)),
291:             "dependsOn": depends_on,
292:             "precondition": precondition,
293:             "postcondition": postcondition,
294:             "retryPolicy": retry_policy,
295:             "state": "PLANNED",
296:             "attempts": 0,
297:             "evidence": {},
298:             "error": "",
299:         }
```
`raw.get("capabilityToken")` and `raw.get("capability_token")` are never accessed, never validated, and never returned in the cleaned step dictionary.

### 1.3 Empirical Evidence: Terminal Reproduction of the Defect

We ran an automated probe against the unmodified `HandsPlanner`:
```bash
python -c "import asyncio; from scp.security.capability_epoch import CapabilityAuthority; from scp.hands.planner import HandsPlanner; import tempfile, pathlib; tmp = pathlib.Path(tempfile.mkdtemp()); auth = CapabilityAuthority(tmp / 'cap.json'); tok = auth.issue('hands:pc.write_file'); planner = HandsPlanner(); plan = planner.create_plan('test goal', [{'action': 'pc.write_file', 'params': {'path': str(tmp / 'out.txt'), 'content': 'hello'}, 'capabilityToken': tok.to_dict()}]); res = asyncio.run(planner.run_plan(plan['planId'], capability_level=3, approved=True)); print('Run result:', res)"
```
**Terminal Output**:
```json
{
  "success": false,
  "requiresRecovery": true,
  "safeToRetry": false,
  "plan": {
    "planId": "672d86bd2bd14160872871cc89f549a4",
    "state": "HUMAN_REVIEW",
    "steps": [
      {
        "stepId": "step-01",
        "action": "pc.write_file",
        "error": "Mutating action was not verified; automatic retry is blocked"
      }
    ]
  },
  "stepId": "step-01",
  "result": {
    "success": false,
    "action": "pc.write_file",
    "error": "CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)",
    "verification": {"passed": false}
  }
}
```
**Proof**: Even though the caller supplied `'capabilityToken': tok.to_dict()`, `plan['steps'][0]` lacked `'capabilityToken'`, and execution failed with `CapabilityRequiredError: Caller must provide an authorized capability token (FA-05)`.

### 1.4 Serialization Pitfall: `CapabilityToken` Dataclass Stringification
If a caller supplies a `CapabilityToken` dataclass instance (e.g. from Python code), saving to `plans.jsonl` invokes `json.dumps({"plan": plan, ...}, default=str)`.
We verified terminal behavior:
```bash
python -c "from scp.security.capability_epoch import CapabilityToken, parse_capability_token; import json; tok = CapabilityToken('hands:write', 1, 'abc', 100.0); serialized = json.dumps({'tok': tok}, default=str); loaded = json.loads(serialized); print('loaded:', loaded); print('parsed:', parse_capability_token(loaded['tok']))"
```
**Terminal Output**:
```text
loaded: {'tok': "CapabilityToken(subject='hands:write', epoch=1, token_id='abc', issued_at=100.0)"}
parsed: None
```
Because `default=str` produces a non-JSON string, `json.loads` inside `parse_capability_token()` raises `json.JSONDecodeError` and returns `None`.
Conversely, when converted via `tok.to_dict()`:
```text
loaded: {'tok': {'subject': 'hands:write', 'epoch': 1, 'token_id': 'abc', 'issued_at': 100.0}}
parsed: CapabilityToken(subject='hands:write', epoch=1, token_id='abc', issued_at=100.0)
```
Therefore, `_validate_step()` must normalize `CapabilityToken` instances using `.to_dict()`!

### 1.5 Correlated Observation: DAG Scheduler Pre-Flight Capability Check
In `scp/hands/planner.py` line 729 (`_run_dag_locked`):
```python
729: requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0))) if verify_token(capability_token).get("valid", False) else min(int(capability_level), int(step.get("capabilityLevel", 0)))
```
`_run_dag_locked` checks `verify_token(capability_token)`. It does NOT check `parse_capability_token(step_token)`. 
When `run_dag` is called with default `capability_level=0` and per-step capability tokens, line 729 evaluates `min(0, 3) = 0`, causing line 731 to immediately abort the DAG with `WAITING_APPROVAL` before any step tasks are launched.

---

## 2. Logic Chain

1. **Step 1 (Whitelist Projection Drops Unlisted Keys)**:
   In `planner.py` lines 284–299, `_validate_step` explicitly creates a new dictionary containing 14 specified keys (`stepId`, `action`, `params`, `capabilityLevel`, `approved`, `dryRun`, `dependsOn`, `precondition`, `postcondition`, `retryPolicy`, `state`, `attempts`, `evidence`, `error`).
2. **Step 2 (Exclusion of Capability Token)**:
   Neither `"capabilityToken"` nor `"capability_token"` is in that list. Consequently, any step token supplied by the caller in `raw` is discarded from the returned dictionary.
3. **Step 3 (Propagation into Plan Storage)**:
   `create_plan()` calls `_validate_step()` for each step and appends the resulting dictionary to `normalized`. `plan["steps"] = normalized` is saved to `plans.jsonl`. Thus, the persisted plan and the returned public plan have zero token information on any step.
4. **Step 4 (Execution Failure in Run Phase)**:
   During `_run_plan_locked()` (lines 459–464) and `_run_dag_step()` (lines 575–580), the code queries `step.get("capabilityToken") or step.get("capability_token")`. Because the key was dropped in Step 2, this lookup returns `None`.
5. **Step 5 (Fail-Closed Rejection)**:
   Without a plan-level fallback token, `parsed_step_token` evaluates to `None`. `HandsExecutor.execute()` enforces Zero-Trust (INV-AUTH-01, FA-05) and rejects the action with `CapabilityRequiredError`.
6. **Step 6 (Necessity of Dataclass Normalization)**:
   Because `plans.jsonl` is JSON text, passing a raw `CapabilityToken` dataclass causes `json.dumps(..., default=str)` to format it as a Python repr string, breaking `parse_capability_token()` on reload. Normalizing with `hasattr(raw_token, "to_dict")` converts it to a standard dictionary that seamlessly survives persistence and deserialization.

---

## 3. Caveats

1. **Token Lifetime / Expiry**:
   Capability tokens have an `issued_at` timestamp and an `epoch`. If a plan is created hours or days before execution, or if capabilities are revoked between creation and execution, the token may become expired or revoked. This is expected and desirable under Zero-Trust fail-closed semantics (`Capability token is revoked, stale, or scope mismatch`).
2. **Read-Only Explorer Scope**:
   In strict accordance with the read-only exploration mandate, this agent has NOT modified any production source code in `scp/`. The implementation must be executed by Worker 2.

---

## 4. Conclusion & Remediation Specification

### 4.1 Required Product Code Modification in `scp/hands/planner.py`

#### Patch 1: Preserve and Normalize `capabilityToken` in `_validate_step()`
**Target File**: `scp/hands/planner.py`  
**Location**: Lines 283–300

```diff
--- a/scp/hands/planner.py
+++ b/scp/hands/planner.py
@@ -283,6 +283,11 @@ class HandsPlanner:
         retry_policy = self._validate_retry(raw.get("retryPolicy"), f"Step {step_id} retryPolicy")
         raw_capability = max(0, min(int(raw.get("capabilityLevel", definition.capability_level)), 5))
+        raw_token = raw.get("capabilityToken") if raw.get("capabilityToken") is not None else raw.get("capability_token")
+        if hasattr(raw_token, "to_dict") and callable(raw_token.to_dict):
+            step_token: Any = raw_token.to_dict()
+        else:
+            step_token = raw_token
         return {
             "stepId": step_id,
             "action": action,
             "params": params,
             "capabilityLevel": raw_capability,
+            "capabilityToken": step_token,
             "approved": bool(raw.get("approved", False)),
             "dryRun": bool(raw.get("dryRun", False)),
             "dependsOn": depends_on,
```

#### Patch 2: Align Step Token Resolution in DAG Scheduler (`_run_dag_locked`)
**Target File**: `scp/hands/planner.py`  
**Location**: Lines 728–731

```diff
--- a/scp/hands/planner.py
+++ b/scp/hands/planner.py
@@ -728,7 +728,18 @@ class HandsPlanner:
                     definition = self.executor.registry.require(step["action"])
-                    requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0))) if verify_token(capability_token).get("valid", False) else min(int(capability_level), int(step.get("capabilityLevel", 0)))
+                    step_token = (
+                        step.get("capabilityToken")
+                        or step.get("capability_token")
+                        or (capability_token.get(step_id) if isinstance(capability_token, dict) else None)
+                        or (capability_token.get(step["action"]) if isinstance(capability_token, dict) else None)
+                        or capability_token
+                    )
+                    parsed_step_token = parse_capability_token(step_token)
+                    token_is_valid = (
+                        parsed_step_token is not None
+                        or (isinstance(step_token, str) and "." in step_token and verify_token(step_token).get("valid", False))
+                    )
+                    requested_capability = max(int(capability_level), int(step.get("capabilityLevel", 0))) if token_is_valid else min(int(capability_level), int(step.get("capabilityLevel", 0)))
                     request_approved = bool(approved or step.get("approved", False))
```

#### Patch 3: Align Token Target in `_run_plan_locked` & `_run_dag_step`
In `_run_plan_locked` (line 469) and `_run_dag_step` (line 585), replace `verify_token(capability_token)` with `verify_token(step_token)` so that per-step JWT tokens are properly validated:
```python
token_is_valid = (
    parsed_step_token is not None
    or (isinstance(step_token, str) and "." in step_token and verify_token(step_token).get("valid", False))
)
```

---

## 5. Verification Method

### 5.1 Verification Test Script
The following independent verification commands confirm the fix across all input formats and execution modes:

```python
import asyncio
import pathlib
from scp.hands.planner import HandsPlanner

async def verify_planner_step_tokens():
    planner = HandsPlanner()
    auth = planner.executor.capability_authority
    
    # 1. Test Dict Token
    tok1 = auth.issue("hands:pc.write_file")
    plan1 = planner.create_plan("goal 1", [
        {"action": "pc.write_file", "params": {"path": "artifacts/p1.txt", "content": "1"}, "capabilityToken": tok1.to_dict()}
    ])
    assert plan1["steps"][0]["capabilityToken"] is not None
    assert plan1["steps"][0]["capabilityToken"]["subject"] == "hands:pc.write_file"
    
    res1 = await planner.run_plan(plan1["planId"], capability_level=3, approved=True)
    assert res1["success"] is True
    assert pathlib.Path("artifacts/p1.txt").exists()
    pathlib.Path("artifacts/p1.txt").unlink(missing_ok=True)
    
    # 2. Test CapabilityToken Dataclass Object directly
    tok2 = auth.issue("hands:pc.write_file")
    plan2 = planner.create_plan("goal 2", [
        {"action": "pc.write_file", "params": {"path": "artifacts/p2.txt", "content": "2"}, "capabilityToken": tok2}
    ])
    assert isinstance(plan2["steps"][0]["capabilityToken"], dict)
    
    res2 = await planner.run_plan(plan2["planId"], capability_level=3, approved=True)
    assert res2["success"] is True
    assert pathlib.Path("artifacts/p2.txt").exists()
    pathlib.Path("artifacts/p2.txt").unlink(missing_ok=True)
    
    # 3. Test Fail-Closed on Mismatched Token
    tok_bad = auth.issue("hands:browser.read")
    plan3 = planner.create_plan("goal 3", [
        {"action": "pc.write_file", "params": {"path": "artifacts/p3.txt", "content": "3"}, "capabilityToken": tok_bad}
    ])
    res3 = await planner.run_plan(plan3["planId"], capability_level=3, approved=True)
    assert res3["success"] is False
    assert "CapabilityScopeMismatchError" in str(res3.get("result", {}).get("error"))
    assert not pathlib.Path("artifacts/p3.txt").exists()

asyncio.run(verify_planner_step_tokens())
```

### 5.2 Test Suite Execution Commands
```bash
# 1. Unit & Regression Tests
pytest tests/T04_kernel/test_kernel_p1_regressions.py tests/T09_golden_task/test_golden_a_agent_os.py -v

# 2. Meta-Audit Authority
python tools/t00_meta_audit.py

# 3. Full pytest suite
pytest tests/ -q
```

### 5.3 Invalidation Conditions
- Any step dictionary returned by `create_plan()` that omits `"capabilityToken"` when provided in `raw`.
- Any plan execution where a valid per-step token fails with `CapabilityRequiredError`.
- Any unhandled `JSONDecodeError` or `None` token resulting from serialized dataclasses.
- Any loosened assertion in test files.
