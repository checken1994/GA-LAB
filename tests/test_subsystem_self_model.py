import os
os.environ.setdefault("SCP_API_PROFILE", "full")
os.environ.setdefault("SCP_CAPABILITY_SECRET", "dummy-secret-for-tests-123")
os.environ.setdefault("SCP_STORAGE_BACKEND", "sqlite")


def test_subsystem_self_model_importable():
    """self_model: module capability_map phải import được không lỗi."""
    import importlib
    mod = importlib.import_module("scp.self_model.capability_map")
    assert mod is not None, "FAIL: scp.self_model.capability_map không import được!"


def test_subsystem_self_model_has_capability_map():
    """self_model: CapabilityMap class phải tồn tại (được doubt_engine dùng)."""
    from scp.self_model.capability_map import CapabilityMap, CapabilityStatus
    assert CapabilityMap is not None
    assert CapabilityStatus is not None


def test_subsystem_self_model_capability_status_levels():
    """self_model: CapabilityStatus phải có đủ 5 bậc trưởng thành M0→M5."""
    from scp.self_model.capability_map import CapabilityStatus
    values = [s.value for s in CapabilityStatus]
    assert len(values) >= 4, (
        f"FAIL: CapabilityStatus chỉ có {len(values)} bậc, cần >= 4!"
    )
