#!/usr/bin/env python3
"""Reality test: explicit egress deny blocks external URLs before DNS/network."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scp.core.url_fetcher import _safe_fetch_url
old=os.environ.get("SCP_EGRESS_MODE")
os.environ["SCP_EGRESS_MODE"]="deny"
try:
    try:
        _safe_fetch_url("https://example.com", timeout=1)
    except ValueError as exc:
        assert "external egress disabled" in str(exc), str(exc)
        print("PASS [1]: external egress denied before network")
    else:
        raise AssertionError("external URL was not denied")
finally:
    if old is None: os.environ.pop("SCP_EGRESS_MODE", None)
    else: os.environ["SCP_EGRESS_MODE"]=old
print("✓ Reality test 4-d-025 PASSED")
