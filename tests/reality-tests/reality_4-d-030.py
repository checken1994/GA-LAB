#!/usr/bin/env python3
"""Reality test: Python autofix and provider loader share file-backed contract."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
llm_fix = (root / "scp/autofix/llm_fix.py").read_text(encoding="utf-8")
provider_keys = (root / "scp/security/provider_keys.py").read_text(encoding="utf-8")
for marker in ["load_openrouter_keys", "ProviderCredentialError"]:
    assert marker in llm_fix, marker
for marker in ["file_env = f\"{slot}_FILE\"", "_FILE", "Path(file_ref)"]:
    assert marker in provider_keys, marker
print("PASS [1]: llm_fix uses canonical provider loader")
print("PASS [2]: provider loader supports file-backed key references")
print("Reality test 4-d-030 PASSED")
