import os
os.environ.setdefault("SCP_API_PROFILE", "full")
os.environ.setdefault("SCP_CAPABILITY_SECRET", "dummy-secret-for-tests-123")
os.environ.setdefault("SCP_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("SCP_TOP_SYSTEMS_EGRESS", "0")

def test_brain_alias_works():
    """
    Subsystem 'brain' is now a legacy alias for 'error_store.KnowledgeStore'.
    Ensure the alias is valid and doesn't break.
    """
    try:
        from scp.brain.brain import KnowledgeStore
        assert KnowledgeStore is not None
    except ImportError as e:
        assert False, f"Failed to import KnowledgeStore via scp.brain: {e}"
