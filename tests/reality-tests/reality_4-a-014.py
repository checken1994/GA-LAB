from pathlib import Path
"""Reality test for Fix 4-a-014: llm_gateway client init race condition.

Before fix: `_client` was lazily initialized with a bare check-then-set:
    if self._client is None:
        self._client = httpx.AsyncClient(...)
Two concurrent chat()/_call_model() calls could both see _client is None,
both create an httpx.AsyncClient, and one would leak (never closed).

After fix: asyncio.Lock + double-checked init. Only the first concurrent
caller creates _client; subsequent callers see it set + skip the lock
entirely (no contention on the hot path).

DNA principles exercised:
  #2  (vòng lặp khép kín — reality test of the fix, not just the fix)
  #9  (no harm — leaked httpx clients accumulate connections + FDs)
  #22 (PASS ≠ TRUE — old code "worked" but silently leaked under concurrency)
  #26 (reality test — execute + cross-check the lock pattern)
"""
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

FILE = str(Path(__file__).resolve().parents[2]) + '/scp/llm_gateway/client.py'

# TEST 0 — file exists (DNA #19)
assert os.path.isfile(FILE), f"FAIL: file missing: {FILE}"
print("PASS [0/3]: client.py exists")

with open(FILE) as f:
    src = f.read()

tree = ast.parse(src)

# ---------------------------------------------------------------------------
# TEST 1 — OpenRouterProvider has an asyncio.Lock instance assigned in
# __init__ (or _client is created at module import / app startup —
# alternative accepted). OllamaProvider must NOT exist: local Ollama was
# removed from the deployment and its provider layer was deleted from the
# gateway (Clean Workspace — dead code is removed, not config-gated).
# ---------------------------------------------------------------------------
def _class_has_client_lock(class_node: ast.ClassDef) -> bool:
    """Return True if __init__ assigns self._client_lock = asyncio.Lock()
    (or self._client = httpx.AsyncClient(...) at module/class scope)."""
    for node in ast.walk(class_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if (isinstance(tgt, ast.Attribute)
                                and isinstance(tgt.attr, str)
                                and tgt.attr == "_client_lock"):
                            return True
                # also accept: self._client = httpx.AsyncClient(...) at init (module-level init)
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if (isinstance(tgt, ast.Attribute)
                                and isinstance(tgt.attr, str)
                                and tgt.attr == "_client"):
                            # If the value is httpx.AsyncClient(...) — module-level init
                            v = sub.value
                            if isinstance(v, ast.Call):
                                f = v.func
                                name = None
                                if isinstance(f, ast.Attribute):
                                    name = f.attr
                                elif isinstance(f, ast.Name):
                                    name = f.id
                                if name == "AsyncClient":
                                    return True
    return False


classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
assert "OllamaProvider" not in classes, (
    "FAIL: OllamaProvider still exists in the gateway — local Ollama was "
    "removed from the deployment; the dead provider layer must be deleted, "
    "not kept behind config."
)
assert "OpenRouterProvider" in classes, "FAIL: OpenRouterProvider class not found"

for cname in ("OpenRouterProvider",):
    cn = classes[cname]
    has_lock = _class_has_client_lock(cn)
    assert has_lock, (
        f"FAIL: {cname}.__init__ does NOT assign self._client_lock = asyncio.Lock() "
        f"and does NOT create _client at module-level. Race condition persists."
    )
    print(f"PASS [1/3]: {cname} has asyncio.Lock (or module-level _client init)")

# ---------------------------------------------------------------------------
# TEST 2 — No bare check-then-set without a lock (DNA #22: PASS ≠ TRUE).
# Pattern: `if self._client is None: self._client = httpx.AsyncClient(...)`
# without an `async with self._client_lock:` wrapping the assignment.
# We use AST to find every assignment to `self._client = httpx.AsyncClient(...)`
# and verify each is inside an `async with` (lock) block.
# ---------------------------------------------------------------------------
def _find_unprotected_client_inits(class_node: ast.ClassDef) -> list[str]:
    """Return list of locations where self._client = httpx.AsyncClient(...)
    is NOT inside an `async with` block."""
    unprotected = []
    for node in ast.walk(class_node):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.attr, str)
                        and tgt.attr == "_client"):
                    v = node.value
                    if isinstance(v, ast.Call):
                        f = v.func
                        name = None
                        if isinstance(f, ast.Attribute):
                            name = f.attr
                        elif isinstance(f, ast.Name):
                            name = f.id
                        if name == "AsyncClient":
                            # Now check if this assignment is inside an `async with`
                            # We need to look at parents. AST doesn't have parent
                            # pointers by default, so we walk manually.
                            pass
    # Simpler: find every AsyncClient() call inside the class body's async methods
    # and for each, check whether the enclosing context is inside an `async with`.
    # We do this by recursively walking async methods and tracking the with-context.
    def _walk_with_context(node, in_async_with: bool):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.attr, str)
                        and tgt.attr == "_client"):
                    v = node.value
                    if isinstance(v, ast.Call):
                        f = v.func
                        name = None
                        if isinstance(f, ast.Attribute):
                            name = f.attr
                        elif isinstance(f, ast.Name):
                            name = f.id
                        if name == "AsyncClient" and not in_async_with:
                            unprotected.append(
                                f"line {getattr(node, 'lineno', '?')}: "
                                f"self._client = httpx.AsyncClient(...) NOT inside async with"
                            )
        if isinstance(node, ast.AsyncWith):
            for child in ast.iter_child_nodes(node):
                _walk_with_context(child, True)
            return
        for child in ast.iter_child_nodes(node):
            _walk_with_context(child, in_async_with)

    for child in ast.iter_child_nodes(class_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk_with_context(child, False)
    return unprotected

for cname in ("OpenRouterProvider",):
    cn = classes[cname]
    bad = _find_unprotected_client_inits(cn)
    assert not bad, (
        f"FAIL: {cname} has unprotected self._client = httpx.AsyncClient(...) — "
        f"race condition persists. Locations:\n  " + "\n  ".join(bad)
    )
    print(f"PASS [2/3]: {cname} — every _client init is inside `async with` (lock)")

# ---------------------------------------------------------------------------
# TEST 3 — Lock is actually used (at least one `async with self._client_lock:`)
# in each class. (DNA #2: vòng lặp khép kín — lock exists AND is used.)
# ---------------------------------------------------------------------------
def _class_uses_lock(class_node: ast.ClassDef) -> bool:
    for node in ast.walk(class_node):
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                ctx = item.context_expr
                # match self._client_lock
                if (isinstance(ctx, ast.Attribute)
                        and isinstance(ctx.attr, str)
                        and ctx.attr == "_client_lock"):
                    return True
    return False

for cname in ("OpenRouterProvider",):
    cn = classes[cname]
    assert _class_uses_lock(cn), (
        f"FAIL: {cname} defines _client_lock but never uses `async with self._client_lock:`"
    )
    print(f"PASS [3/3]: {cname} uses `async with self._client_lock:`")

print("\n✓ Reality test 4-a-014 PASSED (lock pattern + Ollama-free gateway verified)")
