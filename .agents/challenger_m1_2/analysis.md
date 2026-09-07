# Adversarial Security Analysis: GAP-06 Storage Backend Guard Bypass

**Agent**: Challenger 2 (`challenger_m1_2`)  
**Target**: `scp/kernel_storage.py :: make_storage()` & `TaskKernel` constructor  
**Milestone**: Milestone 1 (GAP-06: SQLite SPOF Documentation & Fail-Closed Guard)  
**Date**: 2026-09-07T19:16:30+07:00  
**Status**: COMPLETE — 113 / 113 Tests Blocked / Passed (0 Bypasses Detected)  
**Final Verdict**: **APPROVE**

---

## 1. Executive Summary

Milestone 1 Worker (`worker_m1`) implemented a guard in `scp/kernel_storage.py :: make_storage()` to prevent silent fallback or insecure operations when an unsupported or distributed storage backend is requested.

As Challenger 2, an adversarial penetration test was executed against `make_storage()` and its consumer `TaskKernel`. The test suite subjected the implementation to 113 aggressive attack payloads across 9 distinct categories:
- Command injection & shell metacharacters (`sqlite; rm -rf /`, backticks, `$()`, pipes, etc.)
- SQL injection & escaping patterns (`sqlite' OR '1'='1`, `sqlite; DROP TABLE tasks; --`, etc.)
- Unsupported & distributed database identifiers (`postgres`, `mysql`, `cockroach`, `etcd`, `redis`, `distributed`, `sqlite3`, etc.)
- Substring, prefix, suffix, and boundary manipulation (`sqlite_custom`, `sqlite2`, `sqlite-wal`, `sqlite://`, etc.)
- Case manipulation on unsupported engines (`POSTGRES`, `PoStGrEs`, `MYSQL`, etc.)
- Unicode confusables, Cyrillic/Turkish homoglyphs, and null-byte injection (`SQL\u0130TE`, `ѕԛlіtе`, `ｓｑｌｉｔｅ`, `sqlite\x00`, etc.)
- Type confusion attacks via direct parameter injection (`int`, `bool`, `bytes`, `list`, `dict`, `object`, `function`, `float`)
- Legitimate SQLite variations and environment variable isolation (`sqlite`, `SQLite`, `SQLITE`, whitespace padding, empty string, unset env)
- `TaskKernel` constructor end-to-end fail-closed behavior (ensuring no database artifacts are created on disk upon rejection)

**Result**: **0 bypasses detected across all 113 adversarial vectors**. The guard strictly fails closed, raising `NotImplementedError` (or `AttributeError` for non-string types) and preventing any unauthorized or unsupported backend execution.

---

## 2. Threat Model & Attack Vectors

The target function under test:
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

### Attack Vector Analysis

1. **Exact Set Membership vs Prefix/Regex**:
   The guard relies on `backend in ("sqlite", "")`. Because it does NOT use regex matching, `.startswith("sqlite")`, or substring containment (`"sqlite" in backend`), any extra character (spaces, semicolons, hyphens, numerals) immediately renders `backend in ("sqlite", "")` as `False`.
2. **Case Normalization**:
   `.lower()` normalizes ASCII characters so legitimate variations like `"SQLite"` or `"SQLITE"` resolve to `"sqlite"`. Unsupported engines like `"POSTGRES"` become `"postgres"`, which is not in `("sqlite", "")` and fails closed.
3. **Whitespace Stripping**:
   `.strip()` removes leading and trailing ASCII and Unicode whitespace. However, internal whitespace (e.g. `"sqlite postgres"`) is preserved, resulting in immediate rejection.
4. **Unicode Normalization & Homoglyphs**:
   Python's `.lower()` converts Turkish dotted capital `İ` (`\u0130`) to `i\u0307` (two code points), resulting in `"sqli\u0307te" != "sqlite"`. Cyrillic lookalikes have different Unicode code points (e.g. U+0455 vs U+0073), failing exact equality.
5. **Null Bytes**:
   Python 3 strings allow embedded null bytes `\x00`. When tested, `"sqlite\x00"` is not equal to `"sqlite"` and fails closed.
6. **Type Confusion**:
   If an internal caller passes non-string types (e.g. `int`, `list`, `dict`), invoking `.strip()` immediately raises `AttributeError` before any backend logic can execute. If `bytes` is passed, `b"sqlite".strip().lower()` produces `b'sqlite'`, which fails `b'sqlite' in ("sqlite", "")` because `bytes != str`, raising `NotImplementedError`.

---

## 3. Empirical Test Suite: Structure & Results

The test suite was implemented in `c:\Users\check\Downloads\scp\.agents\challenger_m1_2\run_adversarial_backend_guard.py`.

### Breakdown of Test Results by Category

| Category | Description | Count | Blocked / Expected | Bypasses | Verdict |
|---|---|---|---|---|---|
| **Cat 1** | Command Injection & Shell Metacharacters | 13 | 13 | 0 | **PASS (Fail-Closed)** |
| **Cat 2** | SQL Injection & Escaping Tricks | 10 | 10 | 0 | **PASS (Fail-Closed)** |
| **Cat 3** | Unsupported & Distributed Database Engines | 29 | 29 | 0 | **PASS (Fail-Closed)** |
| **Cat 4** | Substring, Prefix, Suffix & Boundary Attacks | 14 | 14 | 0 | **PASS (Fail-Closed)** |
| **Cat 5** | Case Manipulation on Unsupported Engines | 9 | 9 | 0 | **PASS (Fail-Closed)** |
| **Cat 6** | Unicode Confusables, Homoglyphs & Null Bytes | 9 | 9 | 0 | **PASS (Fail-Closed)** |
| **Cat 7** | Type Confusion Attacks (Direct Parameter) | 10 | 10 | 0 | **PASS (Fail-Closed)** |
| **Cat 8** | Genuine SQLite Variations (Normal Path) | 12 | 12 | 0 | **PASS (Allowed)** |
| **Cat 9** | TaskKernel E2E Fail-Closed Verification | 7 | 7 | 0 | **PASS (Fail-Closed)** |
| **TOTAL** | **Comprehensive Penetration Suite** | **113** | **113** | **0** | **APPROVE** |

### Excerpt of Raw Execution Log

```
================================================================================
[CHALLENGER 2] ADVERSARIAL PENETRATION SUITE: GAP-06 BACKEND GUARD BYPASS
Target: scp.kernel_storage.make_storage()
================================================================================

[*] CATEGORY 1: Command Injection & Shell Metacharacters (Env & Param)
  [BLOCKED] Command injection: 'sqlite; rm -rf /' -> NotImplementedError: Unsupported storage backend 'sqlite; rm -rf /'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite && rm -rf /' -> NotImplementedError: Unsupported storage backend 'sqlite && rm -rf /'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite | cat /etc/passwd' -> NotImplementedError: Unsupported storage backend 'sqlite | cat /etc/passwd'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: '`touch pwned`' -> NotImplementedError: Unsupported storage backend '`touch pwned`'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: '$(touch pwned)' -> NotImplementedError: Unsupported storage backend '$(touch pwned)'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite; touch /tmp/pwned' -> NotImplementedError: Unsupported storage backend 'sqlite; touch /tmp/pwned'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite\nwhoami' -> NotImplementedError: Unsupported storage backend 'sqlite\nwhoami'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite\rwhoami' -> NotImplementedError: Unsupported storage backend 'sqlite\rwhoami'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite\r\nrm -rf /' -> NotImplementedError: Unsupported storage backend 'sqlite\r\nrm -rf /'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: 'sqlite || true' -> NotImplementedError: Unsupported storage backend 'sqlite || true'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: '& echo pwned' -> NotImplementedError: Unsupported storage backend '& echo pwned'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: '; calc.exe' -> NotImplementedError: Unsupported storage backend '; calc.exe'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] Command injection: '| notepad.exe' -> NotImplementedError: Unsupported storage backend '| notepad.exe'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.

...
[*] CATEGORY 6: Unicode Confusables, Homoglyphs & Null Bytes
  [BLOCKED] Unicode/Null payload: 'SQL\u0130TE' -> NotImplementedError: "Unsupported storage backend 'sqli\u0307te'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: 'sql\u0131te' -> NotImplementedError: "Unsupported storage backend 'sql\u0131te'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: '\u0455\u051bl\u0456t\u0435' -> NotImplementedError: "Unsupported storage backend '\u0455\u051bl\u0456t\u0435'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: '\uff53\uff51\uff4c\uff49\uff54\uff45' -> NotImplementedError: "Unsupported storage backend '\uff53\uff51\uff4c\uff49\uff54\uff45'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: 'sql\u200bite' -> NotImplementedError: "Unsupported storage backend 'sql\u200bite'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: 'sql\ufeffite' -> NotImplementedError: "Unsupported storage backend 'sql\ufeffite'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: 'sqlite\x00' -> NotImplementedError: "Unsupported storage backend 'sqlite\x00'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: '\x00sqlite' -> NotImplementedError: "Unsupported storage backend '\x00sqlite'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."
  [BLOCKED] Unicode/Null payload: 'sqlite\x00postgres' -> NotImplementedError: "Unsupported storage backend 'sqlite\x00postgres'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel."

...
[*] CATEGORY 9: TaskKernel Constructor Fail-Closed Verification
  [BLOCKED] TaskKernel failed closed on 'postgres' (DB created: False) -> Unsupported storage backend 'postgres'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on 'mysql' (DB created: False) -> Unsupported storage backend 'mysql'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on 'sqlite; rm -rf /' (DB created: False) -> Unsupported storage backend 'sqlite; rm -rf /'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on '$(touch /tmp/pwned)' (DB created: False) -> Unsupported storage backend '$(touch /tmp/pwned)'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on 'cockroachdb' (DB created: False) -> Unsupported storage backend 'cockroachdb'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on 'distributed' (DB created: False) -> Unsupported storage backend 'distributed'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.
  [BLOCKED] TaskKernel failed closed on 'sqlite3' (DB created: False) -> Unsupported storage backend 'sqlite3'. Only 'sqlite' is currently supported. For distributed deployments, inject a custom Storage instance into TaskKernel.

================================================================================
PENETRATION TEST RESULTS: Total=113 | Passed=113 | Bypasses=0
VERDICT: APPROVE (SCP_STORAGE_BACKEND guard cannot be bypassed; strictly fails closed)
```

---

## 4. Conclusion

The implementation of `make_storage()` in `scp/kernel_storage.py` and its fail-closed integration into `TaskKernel` satisfies all criteria for GAP-06 under SCP DNA principles:
1. It is provably impossible to bypass the guard using command injection, SQL escaping, case manipulation, homoglyphs, or alternative database drivers.
2. It fails closed with an informative `NotImplementedError` explaining how to inject a custom distributed storage instance.
3. No rogue database files are created when initialization fails.
4. Final verdict: **APPROVE**.
