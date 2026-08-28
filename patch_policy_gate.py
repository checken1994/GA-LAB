with open("scp/autofix/policy_gate.py", "r", encoding="utf-8") as f:
    text = f.read()

# Make FORBIDDEN_PATTERNS a tuple to prevent runtime mutation
text = text.replace("FORBIDDEN_PATTERNS: list[ForbiddenPattern] = [", "FORBIDDEN_PATTERNS = (")
text = text.replace("      ),\n]", "      ),\n)")
text = text.replace("self.patterns: list[ForbiddenPattern] = list(FORBIDDEN_PATTERNS)", "self.patterns: list[ForbiddenPattern] = list(FORBIDDEN_PATTERNS)")

with open("scp/autofix/policy_gate.py", "w", encoding="utf-8") as f:
    f.write(text)
