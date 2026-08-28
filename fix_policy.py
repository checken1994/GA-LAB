with open("scp/autofix/policy_gate.py", "r", encoding="utf-8") as f:
    text = f.read()

# Revert the bad tuple conversion
text = text.replace("FORBIDDEN_PATTERNS = (", "FORBIDDEN_PATTERNS: tuple[ForbiddenPattern, ...] = (")
text = text.replace("      ),\n]", "      ),\n)") # I previously did this but maybe there was another bracket?

import ast
try:
    ast.parse(text)
except SyntaxError as e:
    print(f"Still Syntax error: {e}")
    # Let's just manually fix the array declaration via regex
    import re
    text = re.sub(r'FORBIDDEN_PATTERNS.*?\(\s*ForbiddenPattern', 'FORBIDDEN_PATTERNS = (\n    ForbiddenPattern', text, flags=re.DOTALL)
