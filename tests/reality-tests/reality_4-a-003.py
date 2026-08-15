from pathlib import Path
"""Reality test for Fix 4-a-003: threat/audit/prediction routes need admin auth.

Before fix: All 3 route file docstrings claimed "DEAD ROUTE Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â not registered"
but api_server.py:589-611 DOES register all 3 routers. None of the route
decorators had `Depends(verify_admin)` Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â state-changing POST endpoints
(/v105/predictions/run-cycle, /v105/predictions/verify) were unauthenticated.

After fix: Each route decorator has `dependencies=[Depends(verify_admin)]`,
and the "DEAD ROUTE" lie is removed from the file docstrings.

DNA principles exercised:
  #2  (vĂ„â€Ă‚Â²ng lÄ‚Â¡Ă‚ÂºĂ‚Â·p khĂ„â€Ă‚Â©p kĂ„â€Ă‚Â­n Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â reality test of the fix, not just the fix)
  #9  (no harm Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â admin gate closes an unauthenticated state-changing POST)
  #22 (PASS Ä‚Â¢Ă¢â‚¬Â°Ă‚Â  TRUE Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â docstring lied "DEAD ROUTE" while router was live)
  #26 (reality test Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â execute + cross-check, not just trust the comment)
"""
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROUTES_DIR = str(Path(__file__).resolve().parents[2]) + '/scp/api/routes'
FILES = {
    "threat_routes.py": "scp/api/routes/threat_routes.py",
    "audit_routes.py": "scp/api/routes/audit_routes.py",
    "prediction_routes.py": "scp/api/routes/prediction_routes.py",
}

# ---------------------------------------------------------------------------
# TEST 1 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â All 3 route files exist (DNA #19: observation Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â they're real files)
# ---------------------------------------------------------------------------
for name in FILES:
    path = os.path.join(ROUTES_DIR, name)
    assert os.path.isfile(path), f"FAIL: route file missing: {path}"
print("PASS [1/3]: all 3 route files exist")

# ---------------------------------------------------------------------------
# TEST 2 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â No "DEAD ROUTE" in any of the 3 docstrings (DNA #22: docstring must
# not lie Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â reality (api_server.py registers them) must match the docstring).
# We allow "Live Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â admin auth required" as the honest replacement marker is present"
# ---------------------------------------------------------------------------
for name in FILES:
    path = os.path.join(ROUTES_DIR, name)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "DEAD ROUTE" not in content, (
        f"FAIL: {name} still contains the misleading 'DEAD ROUTE' marker in its docstring. "
        f"Reality: api_server.py registers this router. Replace 'DEAD ROUTE' with "
        f"'Live Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â admin auth required (Fix 4-a-003)'."
    )
    assert "Live - admin auth required (Fix 4-a-003)" in content, (
        f"FAIL: {name} does not contain the honest replacement marker is present"
        f"'Live Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â admin auth required (Fix 4-a-003)'."
    )
print("PASS [2/3]: no 'DEAD ROUTE' lie in any of the 3 docstrings; honest 'Live' marker present")

# ---------------------------------------------------------------------------
# TEST 3 Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â Every @router.get/post decorator in each file has
# `dependencies=[Depends(verify_admin)]` (DNA #9: no harm Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â auth gate).
# We also verify verify_admin is imported in each file.
# ---------------------------------------------------------------------------
import re

for name in FILES:
    path = os.path.join(ROUTES_DIR, name)
    with open(path, encoding="utf-8") as f:
        src = f.read()

    # Must import verify_admin (either from scp.api._shared or scp.security.auth)
    assert (
        "verify_admin" in src and
        ("from scp.api._shared import" in src or "from scp.security.auth import" in src)
    ), f"FAIL: {name} does not import verify_admin"
    # Must import Depends from fastapi
    assert "Depends" in src, f"FAIL: {name} does not import Depends from fastapi"

    # Find every @router.get(...) and @router.post(...) decorator line
    decorator_re = re.compile(r"@router\.(get|post|put|delete|patch)\s*\(")
    matches = list(decorator_re.finditer(src))
    assert matches, f"FAIL: no @router.* decorators found in {name}"

    for m in matches:
        # Find the full decorator (up to the matching close paren on the same
        # statement Ä‚Â¢Ă¢â€Â¬Ă¢â‚¬Â decorators may span multiple lines until the closing )
        start = m.start()
        # Locate the closing paren by counting parens
        depth = 0
        end = None
        for i in range(start, len(src)):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end is not None, f"FAIL: unmatched paren in decorator starting at {src[start:start+80]!r}"
        decorator = src[start:end]
        assert "Depends(verify_admin)" in decorator, (
            f"FAIL: {name} decorator missing Depends(verify_admin):\n  {decorator}"
        )

print("PASS [3/3]: every route decorator in all 3 files has Depends(verify_admin)")

print("\nÄ‚Â¢Ă…â€œĂ¢â‚¬Å“ Reality test 4-a-003 PASSED (3/3 assertions)")
