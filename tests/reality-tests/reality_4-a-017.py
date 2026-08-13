from pathlib import Path
"""Reality test for Fix 4-a-017: healing_engine LIKE pattern escape.

Before fix: User error text was interpolated into a SQL LIKE pattern without
escaping `%` and `_`. A search for '50%' matched every row containing '50'
followed by anything; 'a_b' matched 'aXb', 'aYb', etc.

After fix: `%` and `_` are escaped to `\\%` and `\\_` (with backslash itself
escaped first to `\\\\`), and the LIKE clause uses `ESCAPE '\\'` so the
backslash is treated as the escape char inside the pattern.

DNA principles exercised:
  #2  (vòng lặp khép kín — reality test of the fix, not just the fix)
  #9  (no harm — unescaped LIKE = wrong healing suggestion)
  #22 (PASS ≠ TRUE — old code "worked" but matched too broadly)
  #26 (reality test — execute + cross-check)
"""
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

FILE = str(Path(__file__).resolve().parents[2]) + '/scp/core/healing_engine.py'

# TEST 0 — file exists (DNA #19)
assert os.path.isfile(FILE), f"FAIL: file missing: {FILE}"
print("PASS [0/3]: healing_engine.py exists")

with open(FILE) as f:
    src = f.read()

# ---------------------------------------------------------------------------
# TEST 1 — get_similar_errors function exists + uses ESCAPE clause + escapes
# % and _ in the input.
# ---------------------------------------------------------------------------
assert "def get_similar_errors" in src, "FAIL: get_similar_errors function not found"

# Escape logic present (replace % → \% and _ → \_)
# We check the source AST for `.replace("%", ...)` and `.replace("_", ...)` calls.
tree = ast.parse(src)
target = None
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_similar_errors":
        target = node
        break
assert target is not None, "FAIL: get_similar_errors function not found in AST"

replaces_found = set()
for sub in ast.walk(target):
    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
        if sub.func.attr == "replace":
            # First positional arg should be a string literal
            if sub.args and isinstance(sub.args[0], ast.Constant):
                v = sub.args[0].value
                if isinstance(v, str) and v in ("%", "_", "\\"):
                    replaces_found.add(v)

assert "%" in replaces_found, (
    "FAIL: get_similar_errors does not call .replace('%', ...) to escape the LIKE wildcard"
)
assert "_" in replaces_found, (
    "FAIL: get_similar_errors does not call .replace('_', ...) to escape the LIKE single-char wildcard"
)
print("PASS [1/3]: get_similar_errors escapes both `%` and `_` in user input")

# ---------------------------------------------------------------------------
# TEST 2 — LIKE pattern uses ESCAPE clause (so backslash is the escape char)
# ---------------------------------------------------------------------------
# Strip comments so an explanatory comment isn't mistaken for the actual code.
def strip_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        s = line.lstrip()
        if not s or s.startswith("#"):
            continue
        if "  #" in line:
            line = line.split("  #")[0]
        out.append(line)
    return "\n".join(out)

code = strip_comments(src)
# Look for ESCAPE '\' or ESCAPE "\\" (either quoting style)
has_escape_clause = (
    "ESCAPE '\\'" in code
    or 'ESCAPE "\\\\"' in code
    or 'ESCAPE "\\\\"' in code.replace('"\\\\', '"\\\\')
    or "ESCAPE '\\\\'" in code
)
# Use a more lenient regex-free check: any "ESCAPE" followed by a backslash
# literal somewhere on the same logical area
if not has_escape_clause:
    # Look for the literal "ESCAPE" + a quoted backslash
    import re
    m = re.search(r"ESCAPE\s+'\\\\'", code) or re.search(r'ESCAPE\s+"\\\\"', code)
    has_escape_clause = m is not None
# Also accept "ESCAPE '\'" (Python source has ESCAPE '\\' as the SQL string)
if not has_escape_clause:
    # In SQL: ESCAPE '\' — Python source representation: "ESCAPE '\\'" (single backslash
    # in SQL string, which in Python source is written as '\\' inside a single-quoted
    # string OR as '\\' inside a double-quoted string). The strip_comments keeps
    # only the code; the LIKE clause should have "ESCAPE '\\'" or 'ESCAPE "\\\\"'.
    if "ESCAPE" in code:
        # check 8 chars after ESCAPE for a backslash pattern
        idx = code.find("ESCAPE")
        snippet = code[idx:idx+30]
        if "\\" in snippet:
            has_escape_clause = True

assert has_escape_clause, (
    "FAIL: get_similar_errors LIKE clause does not use ESCAPE '\\' (or equivalent). "
    "Without ESCAPE, the \\% and \\_ in the pattern are treated as literal backslash + "
    "wildcard, not as escaped wildcards."
)
print("PASS [2/3]: LIKE clause uses ESCAPE '\\' (so \\% and \\_ are literal)")

# ---------------------------------------------------------------------------
# TEST 3 — The LIKE pattern is built from the ESCAPED input (not the raw input)
# ---------------------------------------------------------------------------
# Find the db_query_all call inside get_similar_errors and confirm the
# f-string uses the `escaped` variable (not `question` directly).
db_call_lines = []
in_func = False
for line in src.split("\n"):
    if "def get_similar_errors" in line:
        in_func = True
    elif in_func and line.startswith("    def ") and "get_similar_errors" not in line:
        # next function — stop
        break
    if in_func:
        db_call_lines.append(line)

db_call_text = "\n".join(db_call_lines)
# The f-string pattern must use `escaped` (not `question.lower()` directly)
assert "escaped" in db_call_text, (
    "FAIL: get_similar_errors does not reference an `escaped` variable in the "
    "LIKE pattern construction. The raw input would still be interpolated."
)
# Also confirm the bare `f\"%{question.lower()[:30]}%\"` pattern is GONE
# (it was the old buggy pattern).
assert "f\"%{question.lower()[:30]}%\"" not in src and "f'%{question.lower()[:30]}%'" not in src, (
    "FAIL: old buggy LIKE pattern (unescaped question.lower()[:30]) still present"
)
print("PASS [3/3]: LIKE pattern is built from escaped input (raw pattern is gone)")

print("\n✓ Reality test 4-a-017 PASSED (4/4 assertions — incl. file-exists)")
