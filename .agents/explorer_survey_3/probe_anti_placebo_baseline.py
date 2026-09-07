#!/usr/bin/env python3
"""Anti-Placebo Baseline Probe (FA-09) — Explorer 3 Survey.

Proves RED baseline for:
- GAP-05: RLock Placebo in storage vs OCC
- GAP-06: Missing storage backend guard in make_storage()
- GAP-08: CapabilityToken forgery without HMAC signature
- GAP-09: Hardcoded fallback secret & missing import guard
"""

import ast
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def probe_gap05_rlock_placebo() -> dict:
    """Probe GAP-05: Verify whether RLock placebo exists or OCC governs concurrency."""
    print("\n[PROBE GAP-05] Investigating RLock in scp/kernel_storage.py...")
    storage_file = PROJECT_ROOT / "scp" / "kernel_storage.py"
    code = storage_file.read_text(encoding="utf-8")
    tree = ast.parse(code)
    
    rlock_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "RLock":
            rlock_found = True
            break
        elif isinstance(node, ast.Name) and node.id == "RLock":
            rlock_found = True
            break

    from scp.kernel_storage import SQLiteKernelStorage
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_probe.db"
        storage = SQLiteKernelStorage(db_path)
        has_tx_lock_attr = hasattr(storage, "_tx_lock")
        storage.close()

    result = {
        "gap": "GAP-05",
        "rlock_in_ast": rlock_found,
        "has_tx_lock_attr": has_tx_lock_attr,
        "status": "ELIMINATED_IN_WORKING_TREE" if not (rlock_found or has_tx_lock_attr) else "RED_RLOCK_PLACEBO_PRESENT"
    }
    print(f"  AST RLock detected: {rlock_found}")
    print(f"  Instance hasattr(_tx_lock): {has_tx_lock_attr}")
    print(f"  Assessment: {result['status']}")
    return result


def probe_gap06_storage_backend_guard() -> dict:
    """Probe GAP-06: Verify if SCP_STORAGE_BACKEND=postgres raises NotImplementedError."""
    print("\n[PROBE GAP-06] Testing SCP_STORAGE_BACKEND=postgres in make_storage()...")
    from scp.kernel_storage import make_storage

    old_val = os.environ.get("SCP_STORAGE_BACKEND")
    os.environ["SCP_STORAGE_BACKEND"] = "postgres"

    raised_not_implemented = False
    returned_sqlite = False

    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_storage.db"
            storage = make_storage(db_path)
            returned_sqlite = (storage.__class__.__name__ == "SQLiteKernelStorage")
            storage.close()
    except NotImplementedError:
        raised_not_implemented = True
    finally:
        if old_val is not None:
            os.environ["SCP_STORAGE_BACKEND"] = old_val
        else:
            os.environ.pop("SCP_STORAGE_BACKEND", None)

    # Check docstring for WARNING
    doc = make_storage.__doc__ or ""
    has_spof_warning = "WARNING" in doc and "SPOF" in doc

    vulnerable = (not raised_not_implemented) and returned_sqlite
    result = {
        "gap": "GAP-06",
        "raised_not_implemented": raised_not_implemented,
        "silently_returned_sqlite": returned_sqlite,
        "has_spof_warning": has_spof_warning,
        "status": "RED_MISSING_GUARD" if vulnerable else "GREEN_GUARD_ENFORCED"
    }
    print(f"  Raised NotImplementedError: {raised_not_implemented}")
    print(f"  Silently returned SQLiteKernelStorage: {returned_sqlite}")
    print(f"  Docstring has SPOF WARNING: {has_spof_warning}")
    print(f"  Assessment: {result['status']}")
    return result


def probe_gap08_token_forgery() -> dict:
    """Probe GAP-08: Test forging token without signature."""
    print("\n[PROBE GAP-08] Testing token forgery against CapabilityAuthority.validate()...")
    from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "cap_state.json"
        auth = CapabilityAuthority(state_file)

        # Attacker crafts forged token without using auth.issue() and without signature
        forged_token = CapabilityToken(
            subject="hands:admin_exec",
            epoch=0,
            token_id="forged-id-without-signature",
            issued_at=time.time(),
        )

        accepted = auth.validate(forged_token, required_subject="hands:admin_exec")

    result = {
        "gap": "GAP-08",
        "forged_token_accepted": accepted,
        "status": "RED_VULNERABLE_TO_FORGERY" if accepted else "GREEN_SIGNATURE_ENFORCED"
    }
    print(f"  Forged token accepted by validate(): {accepted}")
    print(f"  Assessment: {result['status']}")
    return result


def probe_gap09_fallback_secret() -> dict:
    """Probe GAP-09: Test import without SCP_CAPABILITY_SECRET set."""
    print("\n[PROBE GAP-09] Testing module import without SCP_CAPABILITY_SECRET...")
    old_secret = os.environ.pop("SCP_CAPABILITY_SECRET", None)

    import importlib
    import scp.core.capability_token as cap_mod
    importlib.reload(cap_mod)

    used_fallback = (getattr(cap_mod, "_SECRET", None) == b"dev-secret-do-not-use-in-prod-12345")
    has_missing_secret_error = hasattr(cap_mod, "MissingSecretError")

    env_example_path = PROJECT_ROOT / ".env.example"
    env_example_content = env_example_path.read_text(encoding="utf-8") if env_example_path.exists() else ""
    documented_in_env = "SCP_CAPABILITY_SECRET" in env_example_content

    if old_secret is not None:
        os.environ["SCP_CAPABILITY_SECRET"] = old_secret

    result = {
        "gap": "GAP-09",
        "used_fallback_secret": used_fallback,
        "has_missing_secret_error_class": has_missing_secret_error,
        "documented_in_env_example": documented_in_env,
        "status": "RED_HARDCODED_FALLBACK_ACTIVE" if used_fallback else "GREEN_FAIL_CLOSED"
    }
    print(f"  Used fallback secret: {used_fallback}")
    print(f"  Has MissingSecretError class: {has_missing_secret_error}")
    print(f"  Documented in .env.example: {documented_in_env}")
    print(f"  Assessment: {result['status']}")
    return result


def main():
    print("=" * 70)
    print("ANTI-PLACEBO BASELINE VERIFICATION (FA-09 EXPLOIT MANDATE)")
    print("=" * 70)

    r5 = probe_gap05_rlock_placebo()
    r6 = probe_gap06_storage_backend_guard()
    r8 = probe_gap08_token_forgery()
    r9 = probe_gap09_fallback_secret()

    print("\n" + "=" * 70)
    print("SUMMARY RESULTS:")
    print("=" * 70)
    print(f"GAP-05 (Storage RLock Placebo): {r5['status']}")
    print(f"GAP-06 (Storage Backend Guard): {r6['status']}")
    print(f"GAP-08 (Token HMAC Signature):  {r8['status']}")
    print(f"GAP-09 (Fallback Dev Secret):   {r9['status']}")


if __name__ == "__main__":
    main()
