import os
os.environ.setdefault("SCP_API_PROFILE", "full")
os.environ.setdefault("SCP_CAPABILITY_SECRET", "dummy-secret-for-tests-123")
os.environ.setdefault("SCP_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("SCP_TOP_SYSTEMS_EGRESS", "0")


def test_subsystem_data_sources_importable():
    """Free API catalog: module phải import được không lỗi."""
    import importlib
    mod = importlib.import_module("scp.data_sources.free_api_catalog")
    assert mod is not None, f"FAIL: scp.data_sources.free_api_catalog không import được!"
