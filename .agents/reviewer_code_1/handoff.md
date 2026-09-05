# Handoff Report: Reviewer Code 1

**Agent**: `reviewer_code_1` (Adversarial Reviewer / Critic)  
**Timestamp**: 2026-09-05T12:48:00+07:00 (UTC 2026-09-05T05:48:00Z)  
**Task**: Ultra Max Code Review & Runtime Audit — Adversarial Code Review & State Integrity  
**Working Directory**: `c:\Users\check\Downloads\scp\.agents\reviewer_code_1`  
**Handoff Type**: Hard (Task complete)  
**Final Verdict**: **REQUEST_CHANGES**  

---

## 1. Observation

1. **Git State & Topology**:
   - `git rev-parse HEAD`: `683931076ecc8a0c3fa590e1229f10e326833747` (local `main`).
   - `git rev-parse fix/t09-golden-task-debt`: `2ad73759b9897309d1d26cebcfe42f966689937c`.
   - `git rev-parse origin/main`: `c68559b8137378171569b8c1006f850103a3bb2b`.
   - Commits examined on branch:
     - `1d9724a`: `fix(t09): resolve baseline debt FA-04 and T09 tests`
     - `09461ba`: `fixB(kernel): fence orphan sweep, revive bridge replay dedupe, de-poison checkpoint projection, heartbeat long dispatches`
     - `2ad7375`: `fixS(suite): repair T05 free-only failover contracts, pin deterministic WHY gate in golden-B, commit T05 fail-closed conftest`
     - `6839310`: `rule(T00): HARD-CODE 'suite pass != Complete SCP' - machine verdict + language gate`

2. **Code Implementation in `scp/autofix/runner_phases/reality_test.py`**:
   - Lines 46-51:
     ```python
     return {
         "ok": True,
         "status": "VERIFIED",
         "reason": f"reality test passed, exercised {callables_exercised} callables",
         "callables_exercised": callables_exercised
     }
     ```
   - Lines 25-28:
     ```python
     for node in ast.walk(tree):
         if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
             func = getattr(module, node.name, None)
             if callable(func):
     ```
   - Lines 30-36:
     ```python
     mock_args = []
     for param in sig.parameters.values():
         if param.annotation == str: mock_args.append("test")
         elif param.annotation == int: mock_args.append(1)
         elif param.default != inspect.Parameter.empty: mock_args.append(param.default)
         else: mock_args.append("test")
     try:
         func(*mock_args)
     except Exception as e:
         return {"ok": False, "status": "UNVERIFIED", "reason": f"Execution error in {node.name}: {e}"}
     ```

3. **Adversarial Execution Evidence on `reality_test.py`**:
   - Command:
     ```pwsh
     python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_class.py"; p.write_text("class Config:\n    TIMEOUT = 30\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print(run_reality_test(file_path=str(p)))'
     ```
     Result: `{'ok': True, 'status': 'VERIFIED', 'reason': 'reality test passed, exercised 0 callables', 'callables_exercised': 0}`.
   - Command:
     ```pwsh
     python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_kw.py"; p.write_text("def log_event(**kwargs):\n    pass\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print(run_reality_test(file_path=str(p)))'
     ```
     Result: `{'ok': False, 'status': 'UNVERIFIED', 'reason': "Execution error in log_event: log_event() takes 0 positional arguments but 1 was given"}`.
   - Command:
     ```pwsh
     python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_async.py"; p.write_text("async def fail_immediately(x: str):\n    raise RuntimeError(\"Should have crashed!\")\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print(run_reality_test(file_path=str(p)))'
     ```
     Result: `{'ok': True, 'status': 'VERIFIED', 'reason': 'reality test passed, exercised 0 callables', 'callables_exercised': 0}`.
   - Command:
     ```pwsh
     python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_exit.py"; p.write_text("import sys\ndef exit_now():\n    sys.exit(0)\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print("Before"); run_reality_test(file_path=str(p)); print("After")'
     ```
     Result: `Before` printed, `After` never printed; host process terminated immediately with exit code 0.

4. **Implementation of `scp/autofix/evidence_replay.py`**:
   - Lines 13-21:
     ```python
     def get_entry(self, signature: str):
         import os
         if os.environ.get("SCP_SEED_GOLD_EVIDENCE") == "1":
             return {
                 "test_command": "pytest",
                 "buggy_source": "",
                 "gold_source": ""
             }
         return None
     ```
   - Lines 28-29:
     ```python
     def verify(self, *args, **kwargs):
         return {"ok": True, "status": "VERIFIED"}
     ```
   - Lines 41-42:
     ```python
     def compute_bug_signature(*args, **kwargs):
         return "mock_signature"
     ```

5. **Runtime Test Verifications**:
   - `python tools/t00_meta_audit.py`: Exit code 0, `[T00 Meta-Audit] All integrity checks passed (0 new regressions).`
   - `pytest tests/T09_golden_task/ -v`: Exit code 0, 9 passed in 38.86s.
   - `pytest tests/T04_kernel/test_kernel_p1_regressions.py -v`: Exit code 0, 5 passed in 3.43s.
   - `pytest tests/T05_gateway/test_provider_failover.py tests/T05_gateway/test_provider_timeout_recovery.py -v`: Exit code 0, 7 passed in 2.80s.

---

## 2. Logic Chain

1. *From Observation 2 & Observation 3 (Zero Callables)*:
   `reality_test.py` line 46 unconditionally returns `status: "VERIFIED"` even when `callables_exercised == 0`.
   In `reports/expert-panel/MISSION_QUEUE.md` line 22, the specification dictates: *"chưa exercise được → UNVERIFIED (rollback tiếp diễn — trung thực)"*.
   Under DNA #22 (*PASS ≠ TRUE*), a test that executes zero assertions or callables cannot certify verification. Therefore, returning `VERIFIED` on 0 callables is an architectural defect and false positive.
2. *From Observation 2 & Observation 3 (Class Methods & Async Functions)*:
   `ast.walk(tree)` locates `ast.FunctionDef`, but `getattr(module, node.name, None)` only looks up module-level attributes. All methods defined inside classes evaluate to `None` and are skipped.
   Additionally, `async def` functions are parsed as `ast.AsyncFunctionDef`, which fails `isinstance(node, ast.FunctionDef)` and are also skipped.
   Consequently, class-based and async modules consistently receive `callables_exercised == 0` and false `VERIFIED`.
3. *From Observation 2 & Observation 3 (Kwargs Crash)*:
   `sig.parameters.values()` does not inspect `param.kind`. Positional arguments are passed into `**kwargs` or keyword-only arguments, resulting in Python raising `TypeError`.
   This exception is caught and returned as `UNVERIFIED`, causing correct fixes to be falsely rejected and rolled back.
4. *From Observation 3 (Process Termination Vulnerability)*:
   `reality_test.py` runs within the runner's host Python process. When `sys.exit()` is executed, `SystemExit` is raised. Because `SystemExit` inherits from `BaseException` and not `Exception`, it escapes uncaught, abruptly killing the test runner.
   There is also no timeout protection against infinite loops.
5. *From Observation 4 (Integrity Debt in `evidence_replay.py`)*:
   `evidence_replay.py` remains a pure mock/stub implementation, relying on `SCP_SEED_GOLD_EVIDENCE="1"` to fake gold evidence entries. Wave 1 M1 explicitly requires real SHA256 signature computation and re-scan comparison.
6. *From Observation 1 & Observation 5 (Kernel and Gateway Repairs)*:
   Commits `09461ba` and `2ad7375` successfully fix the four P1 kernel defects and provide hermetic fail-closed isolation for T05 Gateway. These parts are sound and verified.
7. *Synthesis to Verdict*:
   Because `reality_test.py` contains critical vulnerabilities that yield false `VERIFIED` verdicts, false `UNVERIFIED` rollbacks, and potential process termination, the code changes cannot be approved in their current form. Verdict: **REQUEST_CHANGES**.

---

## 3. Caveats

1. **Working Tree Uncommitted L4 Edits**:
   Local changes in `tools/t00_meta_audit.py`, `tests/T00_integrity/test_meta_audit.py`, `tests/T00_integrity/test_pass_never_means_complete_scp.py`, and `tests/T02_contract/test_god_split_semantic_parity.py` are needed to make `t00_meta_audit.py` pass cleanly locally, but trigger L4 Codeowners warnings that require server-side approval on GitHub.
2. **Synchronous Heartbeat in Asyncio**:
   `TaskKernelHandsBridge._heartbeat_until_finished` executes synchronous SQLite calls (`self.kernel.heartbeat`) inside the asyncio event loop thread. Under heavy DB write contention, this could introduce latency to concurrent coroutines.
3. **Watchdog Age Filtering**:
   `auto_reconcile_orphans` filters orphan candidates via `updated_at < cutoff` (default 60s). If a worker claims a lease with a short TTL (e.g. 5s) and dies immediately, the watchdog will not sweep it until 60 seconds after `updated_at`.

---

## 4. Conclusion

The code under review achieves significant progress on Kernel durability and Gateway isolation, but fails adversarial review in the Autofix pipeline:
- **Verdict**: **REQUEST_CHANGES**.
- **Key Blockers to Fix**:
  1. Return `status: "UNVERIFIED"` when `callables_exercised == 0`.
  2. Inspect and exercise class methods and async functions.
  3. Differentiate parameter kinds to prevent `TypeError` on `**kwargs` and keyword-only args.
  4. Catch `SystemExit` / `BaseException` and add timeout protection.
  5. Replace dummy stubs in `evidence_replay.py` with real SHA256 signatures.

---

## 5. Verification Method

To independently verify all findings and reproduce the adversarial test results:

1. **Verify False VERIFIED on 0 Callables**:
   ```pwsh
   python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_class.py"; p.write_text("class Config:\n    TIMEOUT = 30\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print(run_reality_test(file_path=str(p)))'
   ```
   *Observed*: `{'ok': True, 'status': 'VERIFIED', 'reason': 'reality test passed, exercised 0 callables', 'callables_exercised': 0}`.

2. **Verify False UNVERIFIED on Kwargs**:
   ```pwsh
   python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_kw.py"; p.write_text("def log_event(**kwargs):\n    pass\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print(run_reality_test(file_path=str(p)))'
   ```
   *Observed*: `{'ok': False, 'status': 'UNVERIFIED', 'reason': "Execution error in log_event: log_event() takes 0 positional arguments but 1 was given"}`.

3. **Verify Host Process Termination via `sys.exit()`**:
   ```pwsh
   python -c 'import tempfile, pathlib; p = pathlib.Path(tempfile.gettempdir()) / "dummy_exit.py"; p.write_text("import sys\ndef exit_now():\n    sys.exit(0)\n"); from scp.autofix.runner_phases.reality_test import run_reality_test; print("Before"); run_reality_test(file_path=str(p)); print("After")'
   ```
   *Observed*: `Before` is printed, process terminates immediately, `After` is never reached.

4. **Verify Kernel & Gateway Regression Tests**:
   ```pwsh
   pytest tests/T04_kernel/test_kernel_p1_regressions.py -v
   pytest tests/T05_gateway/test_provider_failover.py tests/T05_gateway/test_provider_timeout_recovery.py -v
   pytest tests/T09_golden_task/ -v
   python tools/t00_meta_audit.py
   ```
