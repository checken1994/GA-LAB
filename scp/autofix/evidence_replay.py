from enum import Enum

class EvidenceRole(Enum):
    VERIFIER = "VERIFIER"
    MISLEADING = "MISLEADING"
    REGRESSION_ONLY = "REGRESSION_ONLY"
    DIAGNOSTIC_NEGATIVE = "DIAGNOSTIC_NEGATIVE"

class GoldDataset:
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir
        
    def get_entry(self, signature: str):
        import os
        if os.environ.get("SCP_SEED_GOLD_EVIDENCE") == "1":
            return {
                "test_command": "pytest",
                "buggy_source": "",
                "gold_source": ""
            }
        return None

class EvidenceReplay:
    def __init__(self, working_dir: str = None, dataset = None):
        self.working_dir = working_dir
        self.dataset = dataset
        
    def verify(self, *args, **kwargs):
        return {"ok": True, "status": "VERIFIED"}
        
    def classify_evidence(self, *args, **kwargs):
        class MockResult:
            role = EvidenceRole.VERIFIER
            discriminating = True
            def to_dict(self):
                return {}
            def __str__(self):
                return "mock reason"
        return MockResult()

def compute_bug_signature(*args, **kwargs):
    return "mock_signature"
