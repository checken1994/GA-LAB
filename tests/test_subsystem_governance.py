import os
os.environ.setdefault("SCP_API_PROFILE", "full")
os.environ.setdefault("SCP_CAPABILITY_SECRET", "dummy-secret-for-tests-123")
os.environ.setdefault("SCP_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("SCP_TOP_SYSTEMS_EGRESS", "0")


def test_subsystem_governance_importable():
    """Governance: module phải import được không lỗi."""
    import importlib
    mod = importlib.import_module("scp.governance")
    assert mod is not None, f"FAIL: scp.governance không import được!"
