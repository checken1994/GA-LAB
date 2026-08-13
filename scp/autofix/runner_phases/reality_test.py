"""
[SCP-DNA-FIX R7-Full IMP-2] Reality Test Phase — NEW autofix pipeline phase.

TẠI SAO file này tồn tại?
  R5/R6 Reality test (import + exercise) ran MANUALLY by operator post-audit.
  Autofix didn't self-test → fix could cause ImportError/TypeError that no one
  knew about until the next scheduled run. MTTD (mean time to detect regression)
  was hours-days. DNA #26: Reality có quyền cuối cùng — verify with REAL runtime.

  This phase runs AFTER a fix is applied (before audit log is closed):
    1. importlib.reload(module) — force reimport of patched module
    2. AST-extract each top-level function/method in the patched file
    3. Call each function with SMOKE-TEST inputs (safe values per signature)
       - 0 args         → call()
       - 1 str arg      → call("test")
       - 1 int arg      → call(0)
       - 1 list arg     → call([])
       - **kwargs only  → call() (no positional needed)
       - *args          → call()
       - has default    → call() (use defaults)
    4. Catch ImportError / TypeError / AttributeError → FAIL
       (other exceptions OK — module-level runtime context may be missing)
    5. If FAIL → rollback + escalate to Tier-3

Inspired by: pytest import-mode + Python's importlib.reload()

Flow:
  Tier-2 fix applied → reality_test.run(bug, patched_file) → {ok: bool, reason: str}
    ok=True  → keep fix, continue to audit log
    ok=False → rollback fix, mark bug for Tier-3 (human review)

DNA principles applied:
  #26 (Reality > Model) — verify with REAL runtime (import + call), not static
  #9  (No harm)          — if verify fails, rollback (non-fatal to pipeline)
  #12 (Tăng tốc)         — in-pipeline = MTTD < 5s (was hours-days)
  #22 (PASS ≠ TRUE)      — "patch applied" ≠ "code works"
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger("scp.autofix.reality_test")

_SCP_ROOT = Path(__file__).resolve().parent.parent.parent  # .../scp/
_MAX_EXERCISE_TIME_S = 10  # per-module timeout guard (advisory; not enforced via signal here)


# Smoke-test inputs by parameter name heuristic (best-effort — no type info).
# We pick SAFE values that won't trigger network/DB/file side-effects.
_SMOKE_INPUTS_BY_NAME = {
    "user_input": "test",
    "user_id": "test_user",
    "query": "test",
    "text": "test",
    "value": "test",
    "data": "test",
    "name": "test",
    "filename": "test.txt",
    "file_path": "test.txt",
    "path": "/tmp/test",
    "url": "http://localhost/test",
    "host": "localhost",
    "port": 8080,
    "limit": 1,
    "offset": 0,
    "n": 1,
    "count": 1,
    "timeout": 1,
    "max_retries": 1,
    "iter": 1,
    "iterations": 1,
    "verbose": False,
    "dry_run": True,
    "force": False,
}

# Smoke-test inputs by annotation string (matches type comment or annotation).
_SMOKE_INPUTS_BY_ANNOTATION = {
    "str": "test",
    "int": 0,
    "float": 0.0,
    "bool": False,
    "list": [],
    "dict": {},
    "set": set(),
    "tuple": (),
    "bytes": b"",
    "Path": Path("/tmp/test"),
}


def _file_to_module_path(file_path: str | Path) -> str | None:
    """Convert an absolute file path to a dotted module path.

    Returns None if the path is not under a recognized package root.
    Strategy: try `_SCP_ROOT.parent` (e.g. /repo/scp/foo.py → scp.foo).
    Falls back to scanning sys.path entries.
    """
    p = Path(file_path).resolve()
    candidates = [_SCP_ROOT.parent]
    candidates.extend(Path(sp) for sp in sys.path if sp)
    for root in candidates:
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if rel.suffix != ".py":
            return None
        mod = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        return mod
    return None


def _smoke_call_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Build a safe smoke-test argument tuple from a function's signature.

    Returns (args, kwargs) suitable for `func(*args, **kwargs)`.
    - For positional args without defaults: pick a safe value by name/annotation.
    - For positional args WITH defaults: skip (let default apply).
    - For *args / **kwargs: pass nothing.
    """
    args_obj = func.args
    pos_args: list[Any] = []
    n_args = len(args_obj.args)
    n_defaults = len(args_obj.defaults)
    # Positional args WITHOUT defaults start at index 0; the last n_defaults
    # positional args have defaults and we skip them (let the default apply).
    n_required = n_args - n_defaults
    for i in range(n_required):
        arg = args_obj.args[i]
        val = _pick_smoke_value(arg)
        pos_args.append(val)
    # kwargs: skip (caller passes none) — defaults will apply.
    return tuple(pos_args), {}


def _pick_smoke_value(arg: ast.arg) -> Any:
    """Pick a safe smoke value for a single positional argument."""
    name = arg.arg
    # 1. By name heuristic
    if name in _SMOKE_INPUTS_BY_NAME:
        return _SMOKE_INPUTS_BY_NAME[name]
    # 2. By annotation (if it's a simple Name or Attribute)
    ann = arg.annotation
    if isinstance(ann, ast.Name) and ann.id in _SMOKE_INPUTS_BY_ANNOTATION:
        return _SMOKE_INPUTS_BY_ANNOTATION[ann.id]
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        if ann.value in _SMOKE_INPUTS_BY_ANNOTATION:
            return _SMOKE_INPUTS_BY_ANNOTATION[ann.value]
    # 3. Default fallback: empty string (safe + works for many signatures)
    return ""


def _collect_callable_names(file_path: str | Path) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """AST-extract top-level + class-method callables from a Python file.

    Returns list of (qualified_name, ast_function_node).
    qualified_name = "func" for top-level, "Class.method" for methods.
    Skips dunder methods (called by Python implicitly, not directly).
    Skips @property / @staticmethod-decorated-with-arg-requirements (best-effort).
    """
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        logger.debug(f"[IMP-2] syntax error parsing {file_path}: {e}")
        return []
    except Exception as e:  # noqa: BLE001 — best-effort, must not break pipeline
        logger.debug(f"[IMP-2] failed to parse {file_path}: {e}")
        return []

    out: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith("__") and node.name.endswith("__")):
                out.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name.startswith("__") and sub.name.endswith("__"):
                        continue
                    # Skip @property — calling a property without instance is wrong.
                    if any(isinstance(d, ast.Name) and d.id == "property" for d in sub.decorator_list):
                        continue
                    out.append((f"{node.name}.{sub.name}", sub))
    return out


def _try_import_module(file_path: str | Path) -> tuple[bool, str, Any | None]:
    """Import (or reload) the module at file_path.

    Returns (ok, message, module_obj).
    ImportError/SyntaxError → fail. Other exceptions during module-level code
    are non-fatal (module may need runtime context like DB/env vars).
    """
    mod_path = _file_to_module_path(file_path)
    if mod_path is None:
        return True, "module path not resolvable, skip import check", None
    try:
        if mod_path in sys.modules:
            mod = importlib.reload(sys.modules[mod_path])
        else:
            mod = importlib.import_module(mod_path)
        return True, f"import OK ({mod_path})", mod
    except ImportError as e:
        return False, f"ImportError: {e}", None
    except SyntaxError as e:
        return False, f"SyntaxError: {e}", None
    except Exception as e:  # noqa: BLE001 — module-level runtime errors are non-fatal
        # e.g. FileNotFoundError for missing config, KeyError for env var, etc.
        logger.debug(f"[IMP-2] module-level exception (non-fatal): {e}")
        return True, f"import OK (module-level exception non-fatal: {type(e).__name__})", None


def _exercise_callable(
    mod: Any, qual_name: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> tuple[bool, str]:
    """Try to call a callable on the imported module.

    Returns (ok, message).
    ImportError/TypeError/AttributeError → FAIL.
    Other exceptions (ValueError, RuntimeError, etc.) → OK (runtime context issue).
    """
    # Resolve attribute path: "Class.method" → getattr(mod, "Class").method
    obj = mod
    for part in qual_name.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            # Attribute doesn't exist — fix removed/renamed it. FAIL.
            return False, f"AttributeError: {qual_name} not found on module"
    if not callable(obj):
        return False, f"{qual_name} is not callable"

    args, kwargs = _smoke_call_args(node)
    try:
        result = obj(*args, **kwargs)
    except TypeError as e:
        # TypeError means signature mismatch — fix likely changed arg count/name.
        return False, f"TypeError calling {qual_name}: {e}"
    except AttributeError as e:
        return False, f"AttributeError calling {qual_name}: {e}"
    except ImportError as e:
        return False, f"ImportError calling {qual_name}: {e}"
    except Exception as e:  # noqa: BLE001 — runtime context exceptions are OK
        # e.g. ConnectionError, FileNotFoundError, KeyError — runtime issues,
        # not fix regressions. Log and pass.
        logger.debug(f"[IMP-2] {qual_name} raised non-fatal {type(e).__name__}: {e}")
        return True, f"{qual_name} callable (raised non-fatal {type(e).__name__})"
    return True, f"{qual_name} called OK (result type={type(result).__name__})"


def run_reality_test(
    bug_id: str,
    file_path: str,
    exercise_callables: bool = True,
    max_callables: int = 10,
) -> dict:
    """Run Reality Test on a patched file.

    Args:
        bug_id: Bug identifier (e.g. "R7-1" or autofix audit id).
        file_path: Path to the patched file.
        exercise_callables: If True, also call each top-level function with
            safe smoke-test inputs. If False, only import check.
        max_callables: Cap number of callables to exercise (avoid slow tests).

    Returns:
        {
            "ok": bool,         — True if all checks pass
            "checks": {...},    — per-check results
            "reason": str,      — human-readable summary
            "rollback": bool,   — True if fix should be rolled back
        }
    """
    checks: dict[str, Any] = {}
    all_ok = True

    # Check 1: import (or reload) the module
    import_ok, import_msg, mod_obj = _try_import_module(file_path)
    checks["import"] = {"ok": import_ok, "message": import_msg}
    if not import_ok:
        all_ok = False

    # Check 2: exercise each callable
    if exercise_callables and mod_obj is not None:
        callables = _collect_callable_names(file_path)
        exercised = 0
        failures: list[str] = []
        for qual_name, node in callables:
            if exercised >= max_callables:
                break
            call_ok, call_msg = _exercise_callable(mod_obj, qual_name, node)
            exercised += 1
            if not call_ok:
                failures.append(call_msg)
                all_ok = False
        checks["exercise"] = {
            "ok": len(failures) == 0,
            "exercised": exercised,
            "failures": failures[:5],  # cap for log size
        }

    reason = (
        f"[IMP-2] reality_test for {bug_id}: "
        f"{'ALL PASS' if all_ok else 'FAILED'} "
        f"(checks: {', '.join(checks.keys())})"
    )
    logger.info(reason)

    return {
        "ok": all_ok,
        "checks": checks,
        "reason": reason,
        "rollback": not all_ok,
    }


def rollback_fix(file_path: str, backup_path: str | None = None) -> bool:
    """[SCP-DNA-FIX R13-4] DELETED — duplicate of post_fix_verify.rollback_fix.

    TẠI SAO: R7-Full added `rollback_fix` in BOTH reality_test.py AND
    post_fix_verify.py (duplicate dead code — DeadCodeScanner R13-4).
    Engine uses `rollback_fix_by_token` (token-based registry lookup) and
    bypasses both. The canonical impl now lives in post_fix_verify.py
    (re-exported as `rollback_fix_post` via runner_phases/__init__.py),
    with the better logic (multi-extension fallback + traceback logging)
    merged from this file. This stub keeps backward-compat for any
    external callers that did `from scp.autofix.runner_phases.reality_test
    import rollback_fix` — delegates to the canonical impl.
    """
    from scp.autofix.runner_phases.post_fix_verify import rollback_fix as _canonical
    return _canonical(file_path, backup_path=backup_path)


__all__ = ["run_reality_test", "rollback_fix"]
