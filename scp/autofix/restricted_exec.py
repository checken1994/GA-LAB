"""Restricted compilation for LLM-generated single-function candidates.

This is defense-in-depth, not a substitute for an OS/container sandbox.  The
source policy is deliberately narrow: module docstrings and function
 definitions only; no imports, classes, dunder traversal, or dynamic execution
builtins.  Callers must still run untrusted code in a real isolated process for
higher-risk workloads.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any


class RestrictedSourceError(ValueError):
    """Candidate source violates the restricted single-function contract."""


_FORBIDDEN_CALLS = {"__import__", "eval", "exec", "compile", "open", "input", "breakpoint"}
_MAX_AST_NODES = 512


def _validate_tree(source: str) -> ast.Module:
    if not source or not source.strip():
        raise RestrictedSourceError("empty candidate source")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise RestrictedSourceError(f"invalid candidate syntax: {exc}") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise RestrictedSourceError("candidate AST is too large")
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise RestrictedSourceError(f"forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise RestrictedSourceError("dunder name is not allowed")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise RestrictedSourceError("dunder attribute is not allowed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            raise RestrictedSourceError(f"forbidden call: {node.func.id}")
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        raise RestrictedSourceError("only a module docstring and function definitions are allowed")
    return tree


def compile_restricted_function(
    source: str,
    expected_name: str,
    safe_builtins: Mapping[str, Any],
    filename: str,
) -> Any:
    """Compile one validated function into an allowlisted namespace."""
    tree = _validate_tree(source)
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    target = next((node for node in functions if node.name == expected_name), None)
    if target is None:
        raise RestrictedSourceError(f"function not found: {expected_name}")
    namespace: dict[str, Any] = {"__builtins__": dict(safe_builtins)}
    code = compile(tree, filename, "exec")
    exec(code, namespace, namespace)  # nosec B102 — AST policy and builtins allowlist are enforced above.
    function = namespace.get(expected_name)
    if not callable(function):
        raise RestrictedSourceError(f"compiled target is not callable: {expected_name}")
    return function
