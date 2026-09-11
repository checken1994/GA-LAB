import os
os.environ.setdefault("SCP_API_PROFILE", "full")
os.environ.setdefault("SCP_CAPABILITY_SECRET", "dummy-secret-for-tests-123")
os.environ.setdefault("SCP_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("SCP_TOP_SYSTEMS_EGRESS", "0")


def test_subsystem_web_control_importable():
    """Web control: module phải import được không lỗi."""
    import importlib
    mod = importlib.import_module("scp.web_control")
    assert mod is not None, f"FAIL: scp.web_control không import được!"
