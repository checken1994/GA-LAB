#!/usr/bin/env python3
"""Reality test: Python autofix LLM consumer uses file-backed provider secret loader."""
from pathlib import Path
p=Path(__file__).resolve().parents[2]/"scp/autofix/llm_fix.py"
s=p.read_text(encoding="utf-8")
for marker in ["read_secret", "OPENROUTER_API_KEY_FILE", "OPENROUTER_API_KEY_", "_FILE"]:
    assert marker in s, marker
print("PASS [1]: llm_fix uses file-backed provider secret references")
print("✓ Reality test 4-d-030 PASSED")
