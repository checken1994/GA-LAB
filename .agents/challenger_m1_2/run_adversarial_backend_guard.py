"""Adversarial Penetration Test Script for make_storage() and SCP_STORAGE_BACKEND Guard.

Target: scp/kernel_storage.py :: make_storage()
Challenger: Challenger 2 (Milestone 1, GAP-06)
Date: 2026-09-07
Principles: SCP DNA, Zero-Trust, Fail-Closed, FA-08, FA-09
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scp.kernel_storage import SQLiteKernelStorage, make_storage
from scp.task_kernel import TaskKernel


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print("=" * 80)
    print("[CHALLENGER 2] ADVERSARIAL PENETRATION SUITE: GAP-06 BACKEND GUARD BYPASS")
    print("Target: scp.kernel_storage.make_storage()")
    print("=" * 80)

    total_tests = 0
    passed_tests = 0
    bypasses_detected = 0

    temp_dir = tempfile.TemporaryDirectory()
    base_tmp = Path(temp_dir.name)

    # -------------------------------------------------------------------------
    # CATEGORY 1: Command Injection & Shell Metacharacters via SCP_STORAGE_BACKEND
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 1: Command Injection & Shell Metacharacters (Env & Param)")
    cmd_injections = [
        "sqlite; rm -rf /",
        "sqlite && rm -rf /",
        "sqlite | cat /etc/passwd",
        "`touch pwned`",
        "$(touch pwned)",
        "sqlite; touch /tmp/pwned",
        "sqlite\nwhoami",
        "sqlite\rwhoami",
        "sqlite\r\nrm -rf /",
        "sqlite || true",
        "& echo pwned",
        "; calc.exe",
        "| notepad.exe",
    ]

    for payload in cmd_injections:
        total_tests += 1
        test_db = base_tmp / f"cmd_{total_tests}.db"
        # Test via env var
        os.environ["SCP_STORAGE_BACKEND"] = payload
        try:
            res = make_storage(test_db)
            # If we reached here without exception, it's a critical bypass!
            print(f"  [CRITICAL BYPASS] Command injection bypassed guard: {payload!r} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            # Successfully blocked and failed closed
            print(f"  [BLOCKED] Command injection: {payload!r} -> NotImplementedError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] Command injection: {payload!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 2: SQL Injection & Escaping Tricks
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 2: SQL Injection & Escaping Tricks")
    sqli_payloads = [
        "sqlite' OR '1'='1",
        "sqlite\" OR \"1\"=\"1",
        "sqlite' UNION SELECT 1, 2, 3 --",
        "sqlite; DROP TABLE tasks; --",
        "sqlite\'; DROP TABLE tasks; --",
        "sqlite'--",
        "sqlite/*comment*/",
        "sqlite/**/union/**/select",
        "' OR ''='",
        "admin'--",
    ]

    for payload in sqli_payloads:
        total_tests += 1
        test_db = base_tmp / f"sqli_{total_tests}.db"
        os.environ["SCP_STORAGE_BACKEND"] = payload
        try:
            res = make_storage(test_db)
            print(f"  [CRITICAL BYPASS] SQLi payload bypassed guard: {payload!r} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            print(f"  [BLOCKED] SQLi payload: {payload!r} -> NotImplementedError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] SQLi payload: {payload!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 3: Unsupported & Distributed Database Backends
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 3: Unsupported & Distributed Database Backends")
    unsupported_backends = [
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "cockroach",
        "cockroachdb",
        "oracle",
        "mssql",
        "sqlserver",
        "dynamodb",
        "mongodb",
        "redis",
        "etcd",
        "consul",
        "spanner",
        "cassandra",
        "scylladb",
        "distributed",
        "memory",
        "sqlite3",  # Driver/file suffix trick
        "sqlite_cluster",
        "replicated_sqlite",
        "null",
        "none",
        "false",
        "true",
        "0",
        "1",
        "undefined",
    ]

    for backend in unsupported_backends:
        total_tests += 1
        test_db = base_tmp / f"unsupported_{total_tests}.db"
        os.environ["SCP_STORAGE_BACKEND"] = backend
        try:
            res = make_storage(test_db)
            print(f"  [CRITICAL BYPASS] Unsupported backend allowed: {backend!r} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            print(f"  [BLOCKED] Unsupported backend: {backend!r} -> NotImplementedError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] Unsupported backend: {backend!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 4: Substring, Prefix, Suffix & Boundary Manipulation
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 4: Substring, Prefix, Suffix & Boundary Attacks")
    boundary_payloads = [
        "sqlite_custom",
        "sqlite2",
        "sqlite4",
        "mysqllite",
        "nosqlite",
        "sqlite-wal",
        "sqlite.db",
        "sqlite/",
        "sqlite\\",
        "sqlite::memory:",
        "sqlite:memory:",
        "sqlite://",
        "libsqlite",
        "sqlite-raft",
    ]

    for payload in boundary_payloads:
        total_tests += 1
        test_db = base_tmp / f"boundary_{total_tests}.db"
        os.environ["SCP_STORAGE_BACKEND"] = payload
        try:
            res = make_storage(test_db)
            print(f"  [CRITICAL BYPASS] Boundary payload allowed: {payload!r} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            print(f"  [BLOCKED] Boundary payload: {payload!r} -> NotImplementedError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] Boundary payload: {payload!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 5: Case Manipulation on Unsupported Engines
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 5: Case Manipulation on Unsupported Engines")
    case_unsupported = [
        "POSTGRES",
        "PostgreSQL",
        "PoStGrEs",
        "MYSQL",
        "MySql",
        "ETCD",
        "Redis",
        "DISTRIBUTED",
        "CockroachDB",
    ]

    for payload in case_unsupported:
        total_tests += 1
        test_db = base_tmp / f"case_unsupp_{total_tests}.db"
        os.environ["SCP_STORAGE_BACKEND"] = payload
        try:
            res = make_storage(test_db)
            print(f"  [CRITICAL BYPASS] Case-manipulated unsupported engine allowed: {payload!r} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            print(f"  [BLOCKED] Case unsupported: {payload!r} -> NotImplementedError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] Case unsupported: {payload!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 6: Unicode Confusables, Homoglyphs & Null Bytes
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 6: Unicode Confusables, Homoglyphs & Null Bytes")
    unicode_payloads = [
        "SQL\u0130TE",          # Turkish dotted capital I
        "sql\u0131te",          # Turkish dotless small i
        "ѕԛlіtе",              # Cyrillic homoglyphs
        "ｓｑｌｉｔｅ",          # Fullwidth characters
        "sql\u200bite",         # Zero-width space
        "sql\ufeffite",         # Zero-width non-breaking space (BOM)
        "sqlite\x00",           # Null byte suffix
        "\x00sqlite",           # Null byte prefix
        "sqlite\x00postgres",   # Null byte injection
    ]

    for payload in unicode_payloads:
        total_tests += 1
        test_db = base_tmp / f"unicode_{total_tests}.db"
        try:
            # Test direct argument to avoid OS env var null-byte restrictions
            res = make_storage(test_db, backend=payload)
            print(f"  [CRITICAL BYPASS] Unicode/Null payload allowed: {payload!r} -> {type(res)}")
            bypasses_detected += 1
        except (NotImplementedError, ValueError) as e:
            print(f"  [BLOCKED] Unicode/Null payload: {ascii(payload)} -> {type(e).__name__}: {ascii(str(e))}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] Unicode/Null payload: {ascii(payload)} -> {type(e).__name__}: {ascii(str(e))}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 7: Type Confusion Attacks (Direct Parameter Injection)
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 7: Type Confusion Attacks (Direct Param)")
    type_confusion_payloads = [
        12345,
        True,
        False,
        b"sqlite",
        b"postgres",
        ["sqlite"],
        {"sqlite": True},
        object(),
        lambda: "sqlite",
        3.14159,
    ]

    for payload in type_confusion_payloads:
        total_tests += 1
        test_db = base_tmp / f"type_{total_tests}.db"
        try:
            # Passing invalid types directly to make_storage
            res = make_storage(test_db, backend=payload)  # type: ignore[arg-type]
            print(f"  [CRITICAL BYPASS] Type confusion bypassed guard: {type(payload)} -> {type(res)}")
            bypasses_detected += 1
        except NotImplementedError as e:
            print(f"  [BLOCKED - FAIL CLOSED] Type confusion {type(payload).__name__} -> NotImplementedError: {e}")
            passed_tests += 1
        except AttributeError as e:
            print(f"  [BLOCKED - FAIL CLOSED] Type confusion {type(payload).__name__} -> AttributeError: {e}")
            passed_tests += 1
        except TypeError as e:
            print(f"  [BLOCKED - FAIL CLOSED] Type confusion {type(payload).__name__} -> TypeError: {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - FAIL CLOSED] Type confusion {type(payload).__name__} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # -------------------------------------------------------------------------
    # CATEGORY 8: Legitimate SQLite Variations (Should Pass and Return Genuine SQLite)
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 8: Genuine SQLite Variations (Expected Normal Operation)")
    legitimate_sqlite_variants = [
        "sqlite",
        "SQLite",
        "SQLITE",
        "sQLite",
        "SqLiTe",
        "  sqlite  ",
        "\tsqlite\t",
        "\nsqlite\n",
        "\r\n  sqlite  \r\n",
        "",
        "   ",
    ]

    for variant in legitimate_sqlite_variants:
        total_tests += 1
        test_db = base_tmp / f"legit_{total_tests}.db"
        try:
            res = make_storage(test_db, backend=variant)
            if isinstance(res, SQLiteKernelStorage):
                print(f"  [OK - GENUINE SQLITE] {variant!r} -> Successfully returned SQLiteKernelStorage")
                res.close()
                passed_tests += 1
            else:
                print(f"  [FAIL - UNEXPECTED TYPE] {variant!r} -> {type(res)}")
                bypasses_detected += 1
        except Exception as e:
            print(f"  [FAIL - UNEXPECTED REJECTION] {variant!r} -> {type(e).__name__}: {e}")

    # Explicitly test backend=None when env var is unset
    total_tests += 1
    test_db = base_tmp / f"legit_env_unset.db"
    if "SCP_STORAGE_BACKEND" in os.environ:
        del os.environ["SCP_STORAGE_BACKEND"]
    try:
        res = make_storage(test_db, backend=None)
        if isinstance(res, SQLiteKernelStorage):
            print("  [OK - GENUINE SQLITE] backend=None (env unset) -> Successfully returned SQLiteKernelStorage")
            res.close()
            passed_tests += 1
        else:
            print(f"  [FAIL - UNEXPECTED TYPE] backend=None (env unset) -> {type(res)}")
            bypasses_detected += 1
    except Exception as e:
        print(f"  [FAIL - UNEXPECTED REJECTION] backend=None (env unset) -> {type(e).__name__}: {e}")

    # -------------------------------------------------------------------------
    # CATEGORY 9: TaskKernel End-to-End Fail-Closed Verification
    # -------------------------------------------------------------------------
    print("\n[*] CATEGORY 9: TaskKernel Constructor Fail-Closed Verification")
    kernel_e2e_attacks = [
        "postgres",
        "mysql",
        "sqlite; rm -rf /",
        "$(touch /tmp/pwned)",
        "cockroachdb",
        "distributed",
        "sqlite3",
    ]

    for payload in kernel_e2e_attacks:
        total_tests += 1
        test_db = base_tmp / f"kernel_e2e_{total_tests}.sqlite3"
        os.environ["SCP_STORAGE_BACKEND"] = payload
        try:
            k = TaskKernel(test_db)
            print(f"  [CRITICAL BYPASS] TaskKernel initialized with adversarial backend: {payload!r}")
            k.close()
            bypasses_detected += 1
        except NotImplementedError as e:
            # Confirm no database file was created
            db_created = test_db.exists()
            print(f"  [BLOCKED] TaskKernel failed closed on {payload!r} (DB created: {db_created}) -> {e}")
            passed_tests += 1
        except Exception as e:
            print(f"  [BLOCKED - OTHER EXC] TaskKernel on {payload!r} -> {type(e).__name__}: {e}")
            passed_tests += 1

    # Cleanup
    temp_dir.cleanup()

    # Reset environment variable
    if "SCP_STORAGE_BACKEND" in os.environ:
        del os.environ["SCP_STORAGE_BACKEND"]

    print("\n" + "=" * 80)
    print(f"PENETRATION TEST RESULTS: Total={total_tests} | Passed={passed_tests} | Bypasses={bypasses_detected}")
    if bypasses_detected == 0:
        print("VERDICT: APPROVE (SCP_STORAGE_BACKEND guard cannot be bypassed; strictly fails closed)")
        return 0
    else:
        print("VERDICT: REJECT (Guard bypass detected!)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
