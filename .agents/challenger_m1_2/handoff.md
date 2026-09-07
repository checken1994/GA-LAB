# Handoff Report: Challenger 2 (Milestone 1 — GAP-06 Backend Guard Bypass)

**Working Directory**: `c:\Users\check\Downloads\scp\.agents\challenger_m1_2\`  
**Agent**: Challenger 2 (`challenger_m1_2`)  
**Parent Agent**: `50f4125f-5432-4084-856a-8d91aba6378c` (`parent`)  
**Date**: 2026-09-07T19:17:15+07:00  
**Target**: `scp/kernel_storage.py :: make_storage()` & `TaskKernel` constructor  
**Verdict**: **APPROVE** (Guard cannot be bypassed; strictly fails closed)  

---

## 1. Observation

1. **Guard Implementation in `scp/kernel_storage.py:181-196`**:
   ```python
   def make_storage(db_path: str | Path, backend: str | None = None) -> SQLiteKernelStorage:
       """Create the storage backend for a given path.

       WARNING: SQLite is a Single Point of Failure (SPOF) in distributed deployments.
       It does not support cross-node replication or active-active clustering.
       For high availability or multi-node production setups, a distributed storage backend is required.
       """
       if backend is None:
           backend = os.environ.get("SCP_STORAGE_BACKEND", "sqlite")
       backend = backend.strip().lower()
       if backend in ("sqlite", ""):
           return SQLiteKernelStorage(db_path)
       raise NotImplementedError(
           f"Unsupported storage backend '{backend}'. Only 'sqlite' is currently supported. "
           "For distributed deployments, inject a custom Storage instance into TaskKernel."
       )
   ```

2. **Adversarial Penetration Execution**:
   - Command: `python c:\Users\check\Downloads\scp\.agents\challenger_m1_2\run_adversarial_backend_guard.py`
   - Tested: 113 attack cases across 9 categories (command injection, SQL injection, unsupported engines, boundary/substring tricks, case manipulation, Unicode confusables/homoglyphs/null bytes, type confusion, legitimate variants, and TaskKernel E2E).
   - Raw output excerpt:
     ```
     ================================================================================
     [CHALLENGER 2] ADVERSARIAL PENETRATION SUITE: GAP-06 BACKEND GUARD BYPASS
     Target: scp.kernel_storage.make_storage()
     ================================================================================
     ...
     PENETRATION TEST RESULTS: Total=113 | Passed=113 | Bypasses=0
     VERDICT: APPROVE (SCP_STORAGE_BACKEND guard cannot be bypassed; strictly fails closed)
     ```

3. **Kernel Storage Unit Test Execution**:
   - Command: `pytest tests/T04_kernel/test_kernel_storage.py -v`
   - Output: `16 passed in 0.83s`, exit code 0.

4. **TaskKernel End-to-End Fail-Closed Behavior**:
   - For all adversarial inputs (`postgres`, `mysql`, `sqlite; rm -rf /`, `$(touch /tmp/pwned)`, etc.), `TaskKernel(test_db)` raised `NotImplementedError` immediately during constructor execution, before creating any sqlite file on disk (`test_db.exists() == False`).

---

## 2. Logic Chain

1. **Exact Set Membership vs Heuristics (Observation 1 & 2)**:
   - The validation logic relies on `backend = backend.strip().lower()` followed by `backend in ("sqlite", "")`.
   - Any injected command metacharacter (`;`, `&&`, `|`, `` ` ``, `$()`), SQL injection token (`'`, `"`, `--`), path traversal character (`/`, `\`), or alternative engine name (`postgres`, `mysql`, `cockroach`, `sqlite3`) changes the string so that it does not match `"sqlite"` or `""`.
   - Because set membership check is exact and binary, partial matches (e.g. `sqlite_custom`, `libsqlite`, `sqlite-cluster`) are strictly rejected.

2. **Fail-Closed on Unicode and Case Variations (Observation 1 & 2)**:
   - Case conversion `.lower()` safely maps legitimate inputs (`SQLite`, `SQLITE`, `sQLite`) to `"sqlite"`.
   - For exotic Unicode characters like Turkish dotted capital `İ`, `.lower()` folds to `sqli\u0307te` (two code points), which does not equal `"sqlite"` and raises `NotImplementedError`.
   - Cyrillic lookalikes and fullwidth characters have distinct Unicode code points and are rejected.

3. **Type Confusion Fail-Closed (Observation 2)**:
   - If a caller injects a non-string object (e.g. `int`, `bool`, `list`, `dict`), invoking `.strip()` raises `AttributeError`.
   - If `bytes` is passed, `b'sqlite' in ("sqlite", "")` evaluates to `False` (`bytes != str`), raising `NotImplementedError`.
   - At no point does invalid input trigger fallback or bypass.

4. **Integration Safety (Observation 4)**:
   - `TaskKernel.__init__` delegates storage instantiation to `make_storage(db_path)` when no storage is explicitly injected.
   - When an invalid backend is specified in the environment, the constructor raises `NotImplementedError` before attempting schema migration or database creation.

---

## 3. Caveats

- **Scope Limit**: This review and penetration suite evaluated the backend guard in `make_storage()` and its consumer `TaskKernel`. It did not test HMAC tokens (GAP-08) or secret resolution (GAP-09), which are assigned to other milestones.
- **Custom Injected Storage**: `TaskKernel(storage=custom_storage)` allows dependency injection of custom backends without passing through `make_storage()`. The safety of such external custom storage implementations is the responsibility of the custom storage author.

---

## 4. Conclusion

- **Verdict**: **APPROVE**.
- The `SCP_STORAGE_BACKEND` guard in `scp/kernel_storage.py :: make_storage()` cannot be bypassed.
- It strictly enforces fail-closed behavior, rejecting 100% of tested adversarial payloads (113/113) while allowing genuine SQLite configurations.
- All unit tests pass cleanly.

---

## 5. Verification Method

To independently reproduce and verify this challenger assessment:

1. **Run the Adversarial Penetration Suite**:
   ```pwsh
   python c:\Users\check\Downloads\scp\.agents\challenger_m1_2\run_adversarial_backend_guard.py
   ```
   *Expected Output*:
   ```
   PENETRATION TEST RESULTS: Total=113 | Passed=113 | Bypasses=0
   VERDICT: APPROVE (SCP_STORAGE_BACKEND guard cannot be bypassed; strictly fails closed)
   ```
   *Exit code*: 0.

2. **Run Kernel Storage Unit Tests**:
   ```pwsh
   pytest tests/T04_kernel/test_kernel_storage.py -v
   ```
   *Expected Output*: 16 passed, exit code 0.

3. **Invalidation Conditions**:
   - Any payload in `run_adversarial_backend_guard.py` resulting in `[CRITICAL BYPASS]`.
   - `make_storage(db_path, backend="postgres")` returning an instance instead of raising `NotImplementedError`.
   - `make_storage(db_path, backend="sqlite; rm -rf /")` returning an instance.
