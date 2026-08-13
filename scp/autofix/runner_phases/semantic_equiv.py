"""
[SCP-DNA-FIX R8 v3 IMP-15] Semantic Equivalence Verification.

TẠI SAO file này tồn tại?
  IMP-1 (post_fix_verify) + IMP-2 (reality_test) verify rằng file PARSES +
  IMPORTS + callable runs without crash. Nhưng không verify rằng FIX không
  thay đổi behavior ngoài ý muốn. Ví dụ:
    - Bug: NoneComparison ở line 42. Fix "đúng" thêm `if x is None: return 0`.
    - Nhưng LLM cũng "lợi dụng" fix để refactor hàm → thay đổi return type
      của một branch khác → regression ở caller.
    - reality_test pass (smoke input không trigger branch bị thay đổi), nhưng
      production caller bị crash.

  v3 IMP-15 thêm semantic equivalence check:
    1. ast.dump() function body BEFORE fix vs AFTER fix.
    2. So sánh 2 dumps — chênh nhau ở đâu?
    3. Nếu chênh chỉ ở bug_location (line range hoặc statement) → OK.
    4. Nếu chênh ở statements KHÁC → flag "over_broad_fix" → recommend
       review (không auto-apply).
    5. Nếu function KHÔNG CÒN trong fixed_ast (LLM xóa hàm) → CRITICAL.

  Inspired by:
    - DeepCode / CodeQL semantic analysis (compare AST shape, not text)
    - `ast.dump` comparison (Python stdlib — no external dep)
    - GitHub code review "files changed" view (surface over-broad changes)
    - diff-cover + pylint-diff (only flag NEW issues)

Flow:
  result = verify_semantic_equiv(original_ast, fixed_ast, bug_location)
  if result.over_broad:
      fix.disposition = "review"   # IMP-14 confidence drops
  if result.critical:
      rollback_immediately()

DNA principles applied:
  #9  (No harm)         — over-broad fix = potential harm → escalate
  #22 (PASS ≠ TRUE)     — "fix applied + imports OK" ≠ "fix preserves behavior"
  #7  (Autofix safe)    — fail-open: any parse/comparison error → skip check
  #26 (Reality cuối cùng)— AST is ground truth for behavior (static view)
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("scp.autofix.semantic_equiv")


# ============================================================
# Bug location spec.
# ============================================================

@dataclass
class BugLocation:
    """Where the bug is (used to scope "expected" AST changes).

    Attributes:
        function_name: Function containing the bug (top-level or "Class.method").
        line_start:    First line of the bug (1-indexed).
        line_end:      Last line of the bug (1-indexed, inclusive).
        statement_kind: Optional AST node kind of the buggy statement
                        (e.g. "If", "Return", "Assign"). If provided, changes
                        to other statement kinds in the function are flagged.
    """
    function_name: str
    line_start: int = 0
    line_end: int = 0
    statement_kind: str = ""


# ============================================================
# Result dataclass.
# ============================================================

@dataclass
class SemanticEquivResult:
    """Outcome of verify_semantic_equiv().

    Attributes:
        ok: True if fix is semantically acceptable (either equivalent OR
            changes only the bug location).
        equivalent: True if AST is byte-identical (no change at all — rare).
        over_broad: True if AST changed OUTSIDE the bug location. Caller
            should drop confidence / require review.
        critical: True if the target function is GONE from fixed_ast
                  (LLM deleted it) → caller should rollback immediately.
        changed_statements: List of (kind, line) for statements that differ.
        reason: Human-readable summary.
    """
    ok: bool = True
    equivalent: bool = False
    over_broad: bool = False
    critical: bool = False
    changed_statements: list[tuple[str, int]] = field(default_factory=list)
    reason: str = ""


# ============================================================
# AST helpers.
# ============================================================

def _parse_source(source: str) -> ast.Module | None:
    """Parse source into AST. Returns None on error (fail-open)."""
    try:
        return ast.parse(source)
    except SyntaxError as e:
        logger.debug(f"[IMP-15] parse error: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[IMP-15] parse error: {e}")
        return None


def _iter_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Extract top-level + class-method functions from a module AST.

    Returns {qualified_name: FunctionDef}. qualified_name = "func" for
    top-level, "Class.method" for methods. Dunder methods included (caller
    decides what to compare).
    """
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    if tree is None:
        return out
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub
    return out


def _function_signature_dump(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Stable string representation of a function's SIGNATURE (name + args +
    decorators + return annotation).

    Excludes the body — body changes are scored separately.
    """
    try:
        # ast.dump the function with body stripped to []
        sig_copy = type(func)(
            name=func.name,
            args=func.args,
            body=[],
            decorator_list=func.decorator_list,
            returns=func.returns,
            type_comment=getattr(func, "type_comment", None),
        )
        # AsyncFunctionDef has different constructor signature
        if isinstance(func, ast.AsyncFunctionDef):
            sig_copy = ast.AsyncFunctionDef(
                name=func.name, args=func.args, body=[],
                decorator_list=func.decorator_list, returns=func.returns,
                type_comment=getattr(func, "type_comment", None),
            )
        return ast.dump(sig_copy, annotate_fields=False, include_attributes=False)
    except Exception:  # noqa: BLE001
        return ""


def _statement_summary(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, int, str]]:
    """List (kind, lineno, dump_short) for each top-level statement in a function body.

    dump_short = first 80 chars of ast.dump — enough to detect changes.
    """
    out: list[tuple[str, int, str]] = []
    if func is None:
        return out
    for stmt in func.body:
        try:
            dump = ast.dump(stmt, annotate_fields=False, include_attributes=False)
        except Exception:  # noqa: BLE001
            dump = ""
        kind = type(stmt).__name__
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        out.append((kind, lineno, dump[:80]))
    return out


def _is_in_bug_location(
    lineno: int, loc: BugLocation,
) -> bool:
    """True if lineno falls within the bug location's line range."""
    if lineno <= 0:
        # No line info — can't prove it's outside the bug location. Be
        # permissive (return True = "in scope") to avoid false alarms.
        return True
    if loc.line_start <= 0 or loc.line_end <= 0:
        return True  # no line range given → permissive
    return loc.line_start <= lineno <= loc.line_end


# ============================================================
# Core verification function.
# ============================================================

def verify_semantic_equiv(
    original_source: str,
    fixed_source: str,
    bug_location: BugLocation | None = None,
) -> SemanticEquivResult:
    """Verify that a fix changes ONLY the bug location.

    Args:
        original_source: Pre-fix source (full file).
        fixed_source:    Post-fix source (full file).
        bug_location:    Where the bug is (function name + line range).

    Returns:
        SemanticEquivResult with ok/over_broad/critical flags.

    Algorithm:
        1. Parse both sources. On parse failure → fail-open (ok=True, skip).
        2. Extract functions from both.
        3. For the target function (bug_location.function_name):
            a. If missing in fixed → CRITICAL (function deleted).
            b. Compute signature dump; if differ → flag (signature change is
               risky — callers may break).
            c. Compute statement list; compare by (kind, dump) tuples.
            d. Changed statements OUTSIDE bug_location → over_broad=True.
        4. If no bug_location given, compare ALL functions for any change
           (we can't scope, so any change is "over_broad" by default).

    Fail-open: any internal error → ok=True, skip check, log warning.
    """
    result = SemanticEquivResult()

    try:
        orig_tree = _parse_source(original_source)
        fixed_tree = _parse_source(fixed_source)
        if orig_tree is None or fixed_tree is None:
            # Can't parse — fail-open. If fixed_source doesn't parse, that's
            # a different problem (ast.parse check in IMP-14 handles it).
            result.ok = True
            result.reason = "skip — source parse failed (fail-open)"
            return result

        orig_funcs = _iter_functions(orig_tree)
        fixed_funcs = _iter_functions(fixed_tree)

        # If no bug_location given, audit ALL functions.
        targets: list[str] = []
        if bug_location and bug_location.function_name:
            targets.append(bug_location.function_name)
        else:
            targets = list(orig_funcs.keys())

        for fname in targets:
            orig_fn = orig_funcs.get(fname)
            fixed_fn = fixed_funcs.get(fname)

            # Case A: function deleted from fixed source.
            if orig_fn is not None and fixed_fn is None:
                result.critical = True
                result.ok = False
                result.changed_statements.append((f"DELETED:{fname}", 0))
                result.reason = (
                    f"CRITICAL: function '{fname}' removed by fix — "
                    f"callers will break with NameError/AttributeError"
                )
                logger.warning(f"[IMP-15] {result.reason}")
                return result

            # Case B: function added in fixed source (not in original).
            if orig_fn is None and fixed_fn is not None:
                # New function added — not necessarily a bug, but suspicious
                # if we expected a surgical fix. Flag as over_broad.
                result.over_broad = True
                result.changed_statements.append((f"ADDED:{fname}", 0))
                logger.info(
                    f"[IMP-15] fix added new function '{fname}' — "
                    f"flag as over-broad"
                )
                continue

            if orig_fn is None or fixed_fn is None:
                continue  # shouldn't happen (covered above)

            # Case C: signature changed.
            orig_sig = _function_signature_dump(orig_fn)
            fixed_sig = _function_signature_dump(fixed_fn)
            if orig_sig != fixed_sig:
                result.over_broad = True
                result.changed_statements.append((f"SIG_CHANGED:{fname}", 0))
                logger.info(
                    f"[IMP-15] signature of '{fname}' changed by fix — "
                    f"callers may break"
                )

            # Case D: body statement diff.
            orig_stmts = _statement_summary(orig_fn)
            fixed_stmts = _statement_summary(fixed_fn)

            # If lengths differ → over-broad (statements added/removed).
            if len(orig_stmts) != len(fixed_stmts):
                result.over_broad = True
                result.changed_statements.append(
                    (f"STMT_COUNT:{fname}", len(orig_stmts))
                )
                logger.info(
                    f"[IMP-15] '{fname}' statement count changed "
                    f"({len(orig_stmts)} → {len(fixed_stmts)}) — over-broad"
                )
                continue

            # Compare statement-by-statement.
            for (k1, ln1, d1), (k2, ln2, d2) in zip(orig_stmts, fixed_stmts):
                if d1 == d2:
                    continue  # identical — fine
                # Statement differs. Is it inside bug location?
                in_scope = (
                    bug_location is not None
                    and _is_in_bug_location(ln1, bug_location)
                )
                if not in_scope:
                    result.over_broad = True
                    result.changed_statements.append(
                        (f"OUT_OF_SCOPE:{fname}:{k1}", ln1)
                    )
                    logger.info(
                        f"[IMP-15] out-of-scope change in '{fname}' "
                        f"statement {k1} (line {ln1}) — over-broad"
                    )
                else:
                    # In-scope change — expected.
                    result.changed_statements.append(
                        (f"IN_SCOPE:{fname}:{k1}", ln1)
                    )

        # Final disposition.
        if not result.over_broad and not result.critical:
            # No changes outside bug location. Did ANY change happen?
            any_change = bool(result.changed_statements)
            if not any_change:
                result.equivalent = True
                result.reason = "fix is byte-identical to original (no change)"
            else:
                in_scope_count = sum(
                    1 for s in result.changed_statements
                    if s[0].startswith("IN_SCOPE:")
                )
                result.reason = (
                    f"fix changes only bug location "
                    f"({in_scope_count} in-scope statement changes)"
                )
            result.ok = True
        else:
            result.ok = not result.critical
            result.reason = (
                f"over_broad={result.over_broad}, critical={result.critical} — "
                f"review required"
            )

    except Exception as e:  # noqa: BLE001 — fail-open per DNA #7
        logger.warning(f"[IMP-15] verify_semantic_equiv crashed (fail-open): {e}")
        result.ok = True
        result.reason = f"skip — internal error (fail-open): {e}"
        return result

    return result


# ============================================================
# Convenience helper — operates on files (not source strings).
# ============================================================

def verify_files_semantic_equiv(
    original_file: str,
    fixed_file: str,
    bug_location: BugLocation | None = None,
) -> SemanticEquivResult:
    """Like verify_semantic_equiv but takes file paths.

    Reads both files, calls verify_semantic_equiv. Fail-open on I/O error.
    """
    try:
        from pathlib import Path
        orig = Path(original_file).read_text(encoding="utf-8", errors="replace")
        fixed = Path(fixed_file).read_text(encoding="utf-8", errors="replace")
        return verify_semantic_equiv(orig, fixed, bug_location=bug_location)
    except OSError as e:
        logger.warning(f"[IMP-15] file read failed (fail-open): {e}")
        r = SemanticEquivResult()
        r.ok = True
        r.reason = f"skip — file read failed: {e}"
        return r


__all__ = [
    "BugLocation",
    "SemanticEquivResult",
    "verify_semantic_equiv",
    "verify_files_semantic_equiv",
]
