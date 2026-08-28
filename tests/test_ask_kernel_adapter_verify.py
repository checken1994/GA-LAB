import pytest
from scp.ask_kernel_adapter import AskKernelAdapter

class DummyReq:
    contexts = ["sky is blue"]
    retrieved_context = ""
    question = "what color is the sky?"

def test_verify_response_valid():
    adapter = AskKernelAdapter(db_path=":memory:", trace_path="/tmp")
    req = DummyReq()
    response = {
        "final_answer": "The sky is blue",
        "verdict": "PASS",
        "governance_decision": "UPHOLD",
        "v98_classification": {"provenance": "input_context_only"}
    }
    task = {"task_id": "test_123"}
    
    result = adapter.verify_response(req, response, task)
    assert result["verdict"] == "VERIFIED"
    assert 0.0 <= result["grounded_ratio"] <= 1.0

def test_verify_response_empty_contexts():
    adapter = AskKernelAdapter(db_path=":memory:", trace_path="/tmp")
    req = DummyReq()
    req.contexts = []
    response = {
        "final_answer": "The sky is blue",
        "verdict": "PASS",
        "governance_decision": "UPHOLD",
    }
    task = {"task_id": "test_123"}
    
    result = adapter.verify_response(req, response, task)
    assert result["verdict"] == "CONTRADICTED"
    assert result["grounded_ratio"] == 0.0
