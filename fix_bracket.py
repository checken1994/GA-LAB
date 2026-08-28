with open("scp/autofix/policy_gate.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("    ),\n]\n", "    ),\n)\n")

with open("scp/autofix/policy_gate.py", "w", encoding="utf-8") as f:
    f.write(text)
