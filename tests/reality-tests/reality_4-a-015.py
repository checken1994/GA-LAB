from pathlib import Path
"""Reality test for Fix 4-a-015: image/voice check routes use asyncio.to_thread.

Before fix: /v104/image/check + /v104/voice/check async route handlers called
detect() synchronously (blocking CPU: OCR via Tesseract + Whisper ASR). The
event loop was blocked for the duration of OCR/ASR — slow /v104/image/check
stalled /health and all other async requests.

After fix: detect() is wrapped in `await asyncio.to_thread(...)` so the
event loop stays responsive while the blocking CPU work runs in a thread.

DNA principles exercised:
  #2  (vòng lặp khép kín — reality test of the fix, not just the fix)
  #9  (no harm — blocking I/O starves other async handlers)
  #22 (PASS ≠ TRUE — old code "worked" but stalled the event loop)
  #26 (reality test — AST inspection proves no bare detect() in async route)
"""
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

FILE = str(Path(__file__).resolve().parents[2]) + '/scp/api/routes/v104_routes.py'

# TEST 0 — file exists (DNA #19)
assert os.path.isfile(FILE), f"FAIL: file missing: {FILE}"
print("PASS [0/3]: v104_routes.py exists")

with open(FILE) as f:
    src = f.read()

tree = ast.parse(src)

# ---------------------------------------------------------------------------
# TEST 1 — `to_thread` is present in the file (DNA #19: observation).
# (run_in_executor also accepted as alternative.)
assert "to_thread" in src or "run_in_executor" in src, (
    "FAIL: neither asyncio.to_thread nor run_in_executor is used in v104_routes.py"
)
print("PASS [1/3]: asyncio.to_thread (or run_in_executor) is present")

# ---------------------------------------------------------------------------
# TEST 2 — Inside the /v104/image/check and /v104/voice/check async route
# handlers, every `.detect(...)` call is wrapped in `await asyncio.to_thread(...)`
# (no bare synchronous `detect(` call).
# ---------------------------------------------------------------------------
def _find_bare_detect_in_async_func(tree: ast.Module, func_name: str) -> list[str]:
    """Return list of bare `.detect(...)` calls (NOT inside await asyncio.to_thread)
    in the named async function. Returns location descriptions."""
    bare = []

    # Walk to find the function def
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = node
            break
    if target is None:
        return [f"function {func_name} not found"]

    # Walk function body, tracking whether we're inside asyncio.to_thread(...)
    def _walk(node, in_to_thread: bool):
        if isinstance(node, ast.Await):
            # The inner value should be a Call to asyncio.to_thread
            v = node.value
            if isinstance(v, ast.Call):
                f = v.func
                name = None
                if isinstance(f, ast.Attribute):
                    name = f.attr
                elif isinstance(f, ast.Name):
                    name = f.id
                if name == "to_thread":
                    # Children of this call are inside to_thread
                    for c in ast.iter_child_nodes(v):
                        _walk(c, True)
                    return
            # Otherwise it's an await of something else; descend normally
            for c in ast.iter_child_nodes(node):
                _walk(c, in_to_thread)
            return
        if isinstance(node, ast.Call):
            f = node.func
            # Match .detect(...) (Attribute call) — bare = NOT in_to_thread
            if isinstance(f, ast.Attribute) and f.attr == "detect":
                if not in_to_thread:
                    bare.append(
                        f"line {getattr(node, 'lineno', '?')}: bare .detect() call "
                        f"not wrapped in await asyncio.to_thread(...)"
                    )
                return  # don't descend — we've classified this call
        for c in ast.iter_child_nodes(node):
            _walk(c, in_to_thread)

    for c in ast.iter_child_nodes(target):
        _walk(c, False)
    return bare

for func in ("v104_image_check", "v104_voice_check"):
    bad = _find_bare_detect_in_async_func(tree, func)
    assert not bad, (
        f"FAIL: {func} has bare synchronous .detect() calls not wrapped in "
        f"await asyncio.to_thread(...):\n  " + "\n  ".join(bad)
    )
    print(f"PASS [2/3]: {func} — every .detect() call is wrapped in asyncio.to_thread")

# ---------------------------------------------------------------------------
# TEST 3 — both check routes still exist + are async + still call detect()
# (DNA #2: vòng lặp khép kín — function still does its job, just non-blocking).
# ---------------------------------------------------------------------------
funcs = {n.name: n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
assert "v104_image_check" in funcs, "FAIL: v104_image_check function not found"
assert "v104_voice_check" in funcs, "FAIL: v104_voice_check function not found"
assert isinstance(funcs["v104_image_check"], ast.AsyncFunctionDef), (
    "FAIL: v104_image_check must be async def"
)
assert isinstance(funcs["v104_voice_check"], ast.AsyncFunctionDef), (
    "FAIL: v104_voice_check must be async def"
)

# Confirm both still actually reference detect (otherwise fix was a deletion).
# The detect may appear as a Call `detect(...)` OR as a reference passed to
# `asyncio.to_thread(_image_detector.detect, ...)` — both are valid.
def _has_detect_ref(func_node) -> bool:
    for sub in ast.walk(func_node):
        if isinstance(sub, ast.Attribute) and sub.attr == "detect":
            return True
    return False

assert _has_detect_ref(funcs["v104_image_check"]), (
    "FAIL: v104_image_check no longer references detect — fix is too aggressive"
)
assert _has_detect_ref(funcs["v104_voice_check"]), (
    "FAIL: v104_voice_check no longer references detect — fix is too aggressive"
)
print("PASS [3/3]: both check routes still async + still call detect() (now non-blocking)")

print("\n✓ Reality test 4-a-015 PASSED (5 assertions — incl. file-exists + per-route checks)")
