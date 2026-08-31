#!/usr/bin/env python3
"""Reality-aware release policy for Bandit findings.

Bandit's findings are evidence, not a verdict. This policy keeps every raw
finding in the JSON artifact, then classifies only a small set of mechanically
provable cases as reviewed/accepted. Any HIGH or any MEDIUM that cannot be
proved safe remains actionable and fails the release gate.

`--max-medium` is retained only for backwards-compatible workflow invocation;
a raw count is no longer release authority.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _scope_nodes(scope: ast.AST):
    """Yield nodes in one lexical scope, excluding nested funcs/classes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _enclosing_scope(tree: ast.AST, line: int) -> ast.AST:
    scopes: list[ast.AST] = [tree]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line <= end:
                scopes.append(node)
    return max(scopes, key=lambda n: getattr(n, "lineno", 0))


def _target_has_name(target: ast.AST, name: str) -> bool:
    if isinstance(target, ast.Name):
        return target.id == name
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_has_name(item, name) for item in target.elts)
    return False


def _lookup_assignment(scope: ast.AST, name: str, before_line: int) -> ast.AST | None:
    candidates: list[tuple[int, ast.AST]] = []
    for node in _scope_nodes(scope):
        line = getattr(node, "lineno", 0)
        if not line or line >= before_line:
            continue
        if isinstance(node, ast.Assign) and any(_target_has_name(t, name) for t in node.targets):
            candidates.append((line, node.value))
        elif isinstance(node, ast.AnnAssign) and _target_has_name(node.target, name) and node.value is not None:
            candidates.append((line, node.value))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def _static_prefix(
    expr: ast.AST,
    scope: ast.AST,
    before_line: int,
    seen: set[str] | None = None,
) -> tuple[str, bool]:
    """Return the statically known leading string and whether all is static."""
    seen = seen or set()
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value, True
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            return "", False
        value = _lookup_assignment(scope, expr.id, before_line)
        if value is None:
            return "", False
        return _static_prefix(
            value,
            scope,
            getattr(value, "lineno", before_line),
            seen | {expr.id},
        )
    if isinstance(expr, ast.JoinedStr):
        prefix = ""
        complete = True
        for part in expr.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
                continue
            if isinstance(part, ast.FormattedValue):
                piece, piece_complete = _static_prefix(
                    part.value, scope, before_line, seen.copy()
                )
                if piece_complete:
                    prefix += piece
                    continue
            complete = False
            break
        return prefix, complete
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        left, left_complete = _static_prefix(
            expr.left, scope, before_line, seen.copy()
        )
        if not left_complete:
            return left, False
        right, right_complete = _static_prefix(
            expr.right, scope, before_line, seen.copy()
        )
        return left + right, right_complete
    return "", False


def _anchored_network_url(
    expr: ast.AST, scope: ast.AST, before_line: int
) -> tuple[bool, str]:
    prefix, complete = _static_prefix(expr, scope, before_line)
    if not prefix:
        return False, "url origin is not statically anchored"
    parsed = urlsplit(prefix)
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "url host is not statically known"
    if parsed.scheme == "https":
        pass
    elif parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        pass
    else:
        return False, f"scheme/host not accepted: {parsed.scheme}://{host}"
    if not complete:
        marker = prefix.find("://")
        after_scheme = prefix[marker + 3 :] if marker >= 0 else ""
        # Dynamic interpolation may only begin after the authority has been
        # terminated by '/', '?' or '#'. This rejects `https://host{user}`.
        if not any(ch in after_scheme for ch in "/?#"):
            return False, "dynamic text can still alter the URL authority"
    return True, f"statically anchored {parsed.scheme}://{host}"


def _find_call(tree: ast.AST, line: int, terminal_name: str) -> ast.Call | None:
    matches: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)
        if (
            start <= line <= end
            and _call_name(node.func).split(".")[-1] == terminal_name
        ):
            matches.append(node)
    return min(
        matches,
        key=lambda n: (
            getattr(n, "end_lineno", n.lineno) - n.lineno,
            n.col_offset,
        ),
        default=None,
    )


def _request_url_expr(
    expr: ast.AST, scope: ast.AST, before_line: int
) -> ast.AST | None:
    if isinstance(expr, ast.Name):
        assigned = _lookup_assignment(scope, expr.id, before_line)
        if assigned is None:
            return None
        return _request_url_expr(
            assigned, scope, getattr(assigned, "lineno", before_line)
        )
    if isinstance(expr, ast.Call) and _call_name(expr.func).split(".")[-1] == "Request":
        if expr.args:
            return expr.args[0]
        for kw in expr.keywords:
            if kw.arg in {"url", "fullurl"}:
                return kw.value
    return expr


def _accept_b310(path: Path, line: int) -> tuple[bool, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return False, f"source unavailable/unparseable: {type(exc).__name__}"
    call = _find_call(tree, line, "urlopen")
    if call is None or not call.args:
        return False, "urlopen call could not be resolved"
    scope = _enclosing_scope(tree, line)
    url_expr = _request_url_expr(call.args[0], scope, line)
    if url_expr is None:
        return False, "Request URL could not be resolved"
    return _anchored_network_url(url_expr, scope, line)


def _is_empty_dict(node: ast.AST) -> bool:
    return isinstance(node, ast.Dict) and not node.keys and not node.values


def _accept_b307(path: Path, line: int) -> tuple[bool, str]:
    """Accept only SCP's tightly restricted Hypothesis strategy eval shape."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return False, f"source unavailable/unparseable: {type(exc).__name__}"
    call = _find_call(tree, line, "eval")
    if call is None or len(call.args) < 3:
        return False, "eval is not the three-argument restricted form"
    globals_arg, locals_arg = call.args[1], call.args[2]
    if not (
        isinstance(globals_arg, ast.Dict)
        and len(globals_arg.keys) == 1
        and isinstance(globals_arg.keys[0], ast.Constant)
        and globals_arg.keys[0].value == "__builtins__"
        and _is_empty_dict(globals_arg.values[0])
    ):
        return False, "eval globals do not disable builtins exactly"
    if not (
        isinstance(locals_arg, ast.Dict)
        and len(locals_arg.keys) == 1
        and isinstance(locals_arg.keys[0], ast.Constant)
        and locals_arg.keys[0].value == "st"
        and isinstance(locals_arg.values[0], ast.Name)
        and locals_arg.values[0].id == "st"
    ):
        return False, "eval locals are broader than the Hypothesis strategy namespace"
    scope = _enclosing_scope(tree, line)
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False, "restricted eval is not inside a function"
    arg_names = {arg.arg for arg in scope.args.args}
    if "strategy_call" not in arg_names:
        return False, "strategy_call is not an explicit function parameter"
    has_start_guard = False
    has_end_guard = False
    for node in _scope_nodes(scope):
        if getattr(node, "lineno", line) >= line or not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name == "strategy_call.startswith":
            has_start_guard = True
        elif name == "strategy_call.endswith":
            has_end_guard = True
    if not (has_start_guard and has_end_guard):
        return False, "strategy_call shape guards are missing"
    return (
        True,
        "builtins disabled; locals limited to Hypothesis `st`; strategy shape guarded",
    )


def _accept_b108(path: Path, line: int) -> tuple[bool, str]:
    """Recognize `/tmp` only when it is a bwrap tmpfs mount target."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return False, f"source unavailable/unparseable: {type(exc).__name__}"
    scope = _enclosing_scope(tree, line)
    if (
        not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))
        or scope.name != "build_bwrap_argv"
    ):
        return False, "`/tmp` is not inside build_bwrap_argv"
    for node in ast.walk(scope):
        if isinstance(node, (ast.List, ast.Tuple)):
            values = [
                elt.value if isinstance(elt, ast.Constant) else None
                for elt in node.elts
            ]
            for idx in range(len(values) - 1):
                if values[idx] == "--tmpfs" and values[idx + 1] == "/tmp":
                    return (
                        True,
                        "`/tmp` is the isolated bubblewrap tmpfs mount target, not a host temp-file path",
                    )
    return False, "bwrap --tmpfs /tmp invariant not found"


def classify_medium(finding: dict[str, Any]) -> dict[str, Any]:
    item = dict(finding)
    path = Path(str(finding.get("filename", "")))
    line = int(finding.get("line", 0) or 0)
    test_id = str(finding.get("test_id", ""))
    accepted = False
    reason = "no reality-aware acceptance rule"
    kind = "actionable"
    if test_id == "B310":
        accepted, reason = _accept_b310(path, line)
        kind = "accepted_guard" if accepted else "actionable"
    elif test_id == "B307":
        accepted, reason = _accept_b307(path, line)
        kind = "accepted_guard" if accepted else "actionable"
    elif test_id == "B108":
        accepted, reason = _accept_b108(path, line)
        kind = "false_positive" if accepted else "actionable"
    item["policy_class"] = kind
    item["policy_reason"] = reason
    return item


def evaluate(data: dict[str, Any], legacy_max_medium: int) -> dict[str, Any]:
    findings = list(data.get("findings", []))
    high_findings = [
        f for f in findings if str(f.get("severity", "")).upper() == "HIGH"
    ]
    medium_findings = [
        f for f in findings if str(f.get("severity", "")).upper() == "MEDIUM"
    ]
    classified = [classify_medium(f) for f in medium_findings]
    accepted = [f for f in classified if f["policy_class"] != "actionable"]
    actionable = [f for f in classified if f["policy_class"] == "actionable"]
    ok = not high_findings and not actionable
    return {
        "status": "PASS_REALITY_REVIEWED" if ok else "FAIL",
        "policy": "bandit-reality-v2",
        "high": len(high_findings),
        "raw_medium": len(medium_findings),
        "accepted_medium": len(accepted),
        "actionable_medium": len(actionable),
        "legacy_max_medium": legacy_max_medium,
        "legacy_count_threshold_is_authority": False,
        "total": data.get("total"),
        "accepted": accepted,
        "actionable": actionable,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--max-medium", type=int, required=True)
    args = parser.parse_args()
    data = json.loads(args.summary.read_text(encoding="utf-8"))
    result = evaluate(data, args.max_medium)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["high"]:
        raise SystemExit("Bandit HIGH findings are not allowed")
    if result["actionable_medium"]:
        raise SystemExit(
            f"Bandit has {result['actionable_medium']} actionable MEDIUM finding(s); "
            "raw MEDIUM counts are not accepted as a release baseline"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
